# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501

from odoo import models, api


class Picking(models.Model):
    _inherit = "stock.picking"

    @api.multi
    def action_done(self):
        # TODO: Refactor this moethod, it's early in the morning and I'm too tired make it properly
        origin = self.sale_id and self.sale_id.sudo().auto_purchase_order_id.origin
        if origin:
            sale_origin = self.env['sale.order'].sudo().search([('name', '=', origin)], limit=1)
            if sale_origin and sale_origin.partner_shipping_id == self.partner_id:
                # it's dropshipping
                tmp_carrier = self.carrier_id
                self.carrier_id = False
                if not self.number_of_packages:
                    self.number_of_packages = 1
                res = super(Picking, self).action_done()
                pick_origin = sale_origin.picking_ids.filtered(
                    lambda p: p.partner_id.commercial_partner_id == self.company_id.partner_id
                )
                if pick_origin:
                    tmp_loc = pick_origin.location_id
                    tmp_rec = pick_origin.partner_id
                    pick_origin.location_id = self.location_id
                    pick_origin.partner_id = self.partner_id
                    pick_origin.number_of_packages = self.number_of_packages
                    for l in self.move_line_ids:
                        ol = pick_origin.move_line_ids.filtered(lambda l: l.product_id == l.product_id)
                        ol.qty_done = l.qty_done
                    super(Picking, pick_origin).action_done()
                    self.carrier_tracking_ref = pick_origin.carrier_tracking_ref
                    pick_origin.location_id = tmp_loc
                    pick_origin.partner_id = tmp_rec

                self.carrier_id = tmp_carrier
                return res
            else:
                return super(Picking, self).action_done()
        else:
            return super(Picking, self).action_done()
