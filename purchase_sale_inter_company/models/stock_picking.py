# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501

from odoo import api, models


class Picking(models.Model):
    _inherit = "stock.picking"

    @api.multi
    def button_validate(self):
        res = super(Picking, self).button_validate()
        if self.sale_id and self.sale_id.auto_dropship_purchase_order_id:
            po = self.sale_id.auto_dropship_purchase_order_id.sudo()
            if po.picking_ids and not po.picking_ids[0].carrier_tracking_ref:
                po.picking_ids[0].write({
                    'carrier_tracking_ref': self.carrier_tracking_ref
                })

        return res

    @api.multi
    def send_to_shipper(self):
        if self.sale_id:
            super(Picking, self).send_to_shipper()

    @api.multi
    def _add_delivery_cost_to_so(self):
        if self.sale_id:
            super(Picking, self)._add_delivery_cost_to_so()
