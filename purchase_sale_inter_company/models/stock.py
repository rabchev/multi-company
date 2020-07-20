# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501,C901

from odoo import models, api
from odoo.exceptions import ValidationError


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
                    tmp_loc = pick_origin.location_id
                    tmp_rec = pick_origin.partner_id
                    pick_origin.location_id = pick.location_id
                    pick_origin.partner_id = pick.partner_id
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

                    pick_origin.action_done()
                    pick.carrier_tracking_ref = pick_origin.carrier_tracking_ref
                    pick.carrier_id = pick_origin.carrier_id
                    pick_origin.location_id = tmp_loc
                    pick_origin.partner_id = tmp_rec

        return res
    
    def _replace_move_lines(self, stock_picking, lines):
        
        dest_stock_location = self._get_any_stock_location_dest_id(stock_picking)
        self._delete_leaf_move_lines(stock_picking)

        cpy_lines = []
        all_lines_ids = []
        all_lines_props = []
        for l in lines:
            ll = l.copy()
            all_lines_props.append({'lot_id': l.lot_id.id, 'lot_name': l.lot_id.name,
                      'qty_done': l.qty_done, 'location_dest_id': dest_stock_location.id})
            cpy_lines.append(ll)
            all_lines_ids.append(ll.id)
        for move_line in stock_picking.sudo().move_lines:
            move_lines_ids = []
            for ll in cpy_lines:
                if ll.move_id.sudo().product_id == move_line.sudo().product_id:
                    index = cpy_lines.index(ll)
                    all_lines_props[index]['move_id'] = move_line.id
                    ll.write(all_lines_props[index])
                    move_lines_ids.append(ll.id)
            move_line.sudo().write({'move_line_ids': [(6, 0, move_lines_ids)]})
        stock_picking.sudo().write({'move_line_ids': [(6, 0, all_lines_ids)]})

    def _get_any_stock_location_dest_id(self, stock_picking):
        for move_line in stock_picking.move_lines:
            leaf_lines = [l for l in move_line.sudo().move_line_ids]
            for leaf in leaf_lines:
                if len(leaf.sudo().location_dest_id) > 0:
                    return leaf.sudo().location_dest_id

    def _delete_leaf_move_lines(self, stock_picking):
        for move_line in stock_picking.move_lines:
            leaf_lines = [l for l in move_line.sudo().move_line_ids]
            for leaf in leaf_lines:
                move_line.sudo().write({'move_line_ids': [(2, leaf.id, 0)]})
