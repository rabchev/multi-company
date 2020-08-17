# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501,C901

from odoo import models, api
from odoo.exceptions import ValidationError
from contextlib import contextmanager

@contextmanager
def force_company(env, company_id):
    user_company = env.user.company_id
    env.user.update({'company_id': company_id})
    try:
        yield
    finally:
        env.user.update({'company_id': user_company})

class Picking(models.Model):
    _inherit = "stock.picking"

    @api.multi
    def action_done(self):
        res = super(Picking, self).action_done()
        for pick in self:
            origin_po = pick.sale_id and pick.sale_id.sudo().auto_purchase_order_id or False
            if not origin_po:
                continue

            origin = origin_po.origin
            # FIXME: Quick and dirty hack for Econt specifically. Must be fixed as soon as possible!
            if origin and origin.startswith('SO/EEX'):
                if pick.sale_id.sudo().auto_purchase_order_id.company_id.id != 1:
                    continue

                sale_origin = self.env['sale.order'].sudo().search([('name', '=', origin)], limit=1)
                if sale_origin and sale_origin.partner_shipping_id == pick.partner_id:
                    # it's dropshipping
                    pick_origin = sale_origin.sudo().picking_ids.filtered(
                        lambda p: p.partner_id.commercial_partner_id == pick.company_id.partner_id and p.state in ['assigned', 'done']
                    )
                    origin_count = len(pick_origin)
                    if origin_count < 1:
                        raise ValidationError('Source sale order does not have pickings')
                    if origin_count > 1:
                        raise ValidationError('One sale order cannot have more than one picking per supplier.')
                    # set delivery partner needed for creating the econt DS shipment
                    if 'ds_delivery_partner_id' in self.env['stock.picking']._fields:
                        pick_origin.ds_delivery_partner_id = pick.partner_id
                    if 'ds_delivery_location_id' in self.env['stock.picking']._fields:
                        pick_origin.ds_delivery_location_id = pick.location_id
                    pick_origin.number_of_packages = pick.number_of_packages or 1
                    pick_origin.carrier_id = sale_origin.carrier_id
                    lines = [l for l in pick.move_line_ids]
                    if not lines or len(lines) == 0:
                        raise ValidationError('The picking has no stock move lines.')
                    
                    for prodID in pick_origin.mapped('move_lines.product_id'):
                        pickLen = len(pick.move_lines.filtered(lambda p: p.product_id == prodID))
                        originLen = len(pick_origin.move_lines.filtered(lambda p: p.product_id == prodID))
                        if pickLen != originLen:
                            raise ValidationError('Inconsistent order lines between source and current order.')
                    
                    self._replace_move_lines(pick_origin, lines)
                    
                    if 'ds_delivery_partner_id' in self.env['stock.picking']._fields and 'ds_delivery_location_id' in self.env['stock.picking']._fields:
                        self._validate_picking_force_company(pick_origin, pick_origin.company_id)
                    pick.carrier_tracking_ref = pick_origin.carrier_tracking_ref
                    pick.carrier_id = pick_origin.carrier_id

                    # Replace move lines in the stock moves in the IN type stock pickings
                    company_po = self.env['purchase.order'].sudo().search([('origin', '=', sale_origin.name)]).filtered(
                        lambda p: p.sudo().partner_id.id == 1)
                    for in_stock_picking in company_po.sudo().picking_ids:
                        if '/IN/' in in_stock_picking.name:
                            found = False
                            for l in lines:
                                for ml in in_stock_picking.sudo().move_lines:
                                    if ml.sudo().product_id.id == l.move_id.product_id.id:
                                        found = True
                                        break
                                if found:
                                    break
                            if found:
                                self._replace_move_lines(in_stock_picking, lines)
        
        return res
    
    def _validate_picking_force_company(self, stock_picking, company_id):
        with force_company(self.env, company_id):
                stock_picking.with_context(force_company=company_id.id).button_validate()

    def _replace_move_lines(self, stock_picking, lines):
        
        dest_stock_location = self._get_any_stock_location_dest_id(stock_picking)
        if not dest_stock_location:
            dest_stock_location = False
        stock_location = self._get_any_stock_location_id(stock_picking)
        if not stock_location:
            stock_location = False
        self._delete_leaf_move_lines(stock_picking)

        all_lines_ids = []
        all_lines_props = []
        for l in lines:
            props = {'qty_done': l.qty_done}
            if dest_stock_location:
                props['location_dest_id'] = dest_stock_location.id
            if stock_location:
                props['location_id'] = stock_location.id
            # copy multicompany serial number
            if l.lot_id and l.lot_id.product_id:
                company_lot = stock_picking.env['stock.production.lot'].sudo().create(
                    {'name':  l.lot_id.name, 'product_id':  l.lot_id.product_id.id,
                     'company_id': stock_picking.company_id.id})
                props['lot_id'] = company_lot.id
                props['lot_name'] = company_lot.name
            
            all_lines_props.append(props)
        for move_line in stock_picking.sudo().move_lines:
            move_lines_ids = []
            for l in lines:
                if l.move_id.sudo().product_id == move_line.sudo().product_id:
                    index = lines.index(l)
                    all_lines_props[index]['move_id'] = move_line.id
                    all_lines_props[index]['product_id'] = move_line.sudo().product_id.id
                    all_lines_props[index]['product_uom_id'] = move_line.sudo().product_uom.id
                    
                    # creating new stock move lines
                    ll = self.env['stock.move.line'].sudo().create(all_lines_props[index])

                    move_lines_ids.append(ll.id)
                    all_lines_ids.append(ll.id)
            move_line.sudo().write({'move_line_ids': [(6, 0, move_lines_ids)], 'state': 'assigned'})
        stock_picking.sudo().write({'move_line_ids': [(6, 0, all_lines_ids)]})

    def _get_any_stock_location_dest_id(self, stock_picking):
        for move_line in stock_picking.move_lines:
            leaf_lines = [l for l in move_line.sudo().move_line_ids]
            leafres = False
            for leaf in leaf_lines:
                leafres = leaf
                if len(leaf.sudo().location_dest_id) > 0:
                    return leaf.sudo().location_dest_id
            if leafres:
                return leafres.sudo().location_dest_id
            if stock_picking.location_dest_id:
                return stock_picking.location_dest_id
            return False
    
    def _get_any_stock_location_id(self, stock_picking):
        for move_line in stock_picking.move_lines:
            leaf_lines = [l for l in move_line.sudo().move_line_ids]
            leafres = False
            for leaf in leaf_lines:
                leafres = leaf
                if len(leaf.sudo().location_id) > 0:
                    return leaf.sudo().location_id
            if leafres:
                return leafres.sudo().location_id
            if stock_picking.location_id:
                return stock_picking.location_id
            return False

    def _delete_leaf_move_lines(self, stock_picking):
        for move_line in stock_picking.move_lines:
            leaf_lines = [l for l in move_line.sudo().move_line_ids]
            for leaf in leaf_lines:
                move_line_state = move_line.state
                move_line.sudo().write({'move_line_ids': [(2, leaf.id, 0)], 'state': move_line_state})
