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
                    pick_origin = sale_origin.picking_ids.filtered(
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
                    pick_origin.number_of_packages = pick.number_of_packages = pick.number_of_packages or 1
                    pick_origin.carrier_id = sale_origin.carrier_id
                    lines = [l for l in pick.move_line_ids]
                    if not lines or len(lines) == 0:
                        raise ValidationError('Inconsistent order lines between source and current order.')
                    
                    self._copy_move_lines(pick_origin, lines)
                    
                    # refering origin SO document
                    if pick.origin:
                        so_ref = self.env['sale.order'].sudo().search([('name', '=', pick.origin)], limit=1)
                        if so_ref:
                            # refering client's purchase order
                            if so_ref.client_order_ref:
                                # find the Drop Shipping document and update it's lines to match the OUT stock.picking
                                dp = self.env['stock.picking'].sudo().search([('origin', '=', so_ref.client_order_ref)], limit=1)
                                if dp:
                                    self._copy_move_lines(dp, lines)
                    
                    pick_origin.action_done()
                    pick.carrier_tracking_ref = pick_origin.carrier_tracking_ref
                    pick.carrier_id = pick_origin.carrier_id
                    pick_origin.location_id = tmp_loc
                    pick_origin.partner_id = tmp_rec

        return res
    
    def _copy_move_lines(self, stock_picking, lines):
        cpy_lines = []
        all_lines_ids = []
        for l in lines:
            ll = l.copy()
            cpy_lines.append(ll)
            all_lines_ids.append(ll.id)
        for move_line in stock_picking.move_lines:
            move_lines_ids = []
            for ll in cpy_lines:
                if ll.move_id.product_id == move_line.product_id:
                    move_lines_ids.append(ll.id)
                    ll.move_id = move_line
            move_line.update({'move_line_ids': [(6, 0, move_lines_ids)]})
        stock_picking.update({'move_line_ids': [(6, 0, all_lines_ids)]})

