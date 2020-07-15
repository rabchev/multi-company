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
                    
                    for ol in pick_origin.move_line_ids:
                        qty_done_sum = 0
                        i = 0
                        for l in lines:
                            if l.product_id == ol.product_id:
                                qty_done_sum = qty_done_sum + l.qty_done
                                i += 1
                        
                        ol.qty_done = qty_done_sum
                        ol.lot_id = lines[0].lot_id
                    
                    if len(lines) != i:
                        raise ValidationError('Inconsistent order lines between source and current order.')
                    
                    pick_origin.action_done()
                    pick.carrier_tracking_ref = pick_origin.carrier_tracking_ref
                    pick.carrier_id = pick_origin.carrier_id
                    pick_origin.location_id = tmp_loc
                    pick_origin.partner_id = tmp_rec

        return res
