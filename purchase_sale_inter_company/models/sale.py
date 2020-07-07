# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501

from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    auto_purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Source Purchase Order',
        readonly=True,
        copy=False
    )

    @api.multi
    def _action_confirm(self):
        super(SaleOrder, self)._action_confirm()
        po = self.env['purchase.order']
        for order in self:
            if order.auto_purchase_order_id:
                for line in order.order_line:
                    if line.auto_purchase_line_id:
                        line.auto_purchase_line_id.sudo() \
                            .write({'price_unit': line.price_unit})
            elif order.partner_id.commercial_partner_id.id != order.company_id.partner_id.id:
                receiving_company = po.find_company_from_partner(order.partner_id)
                if receiving_company:
                    po = order.sudo().with_context(force_company=receiving_company.id) \
                        ._create_inter_company_purchase_order(receiving_company.id)
                    order.auto_purchase_order_id = po.id

    def _create_inter_company_purchase_order(self, receiving_company_id):
        self.ensure_one()
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']
        receiving_company = self.env['res.company'].browse(receiving_company_id)
        selling_company = self.company_id
        # check intercompany product
        PurchaseOrder.check_intercompany_product(receiving_company, self.order_line)
        po = PurchaseOrder.create(
            self._prepare_purchase_order(
                selling_partner=selling_company.partner_id,
                selling_company=selling_company,
                receiving_company=receiving_company,
            )
        )
        for sale_line in self.order_line:
            po_line_vals = self._prepare_purchase_order_line(
                product_id=sale_line.product_id,
                product_qty=sale_line.product_qty,
                product_uom=sale_line.product_uom,
                price_unit=sale_line.price_unit,
                po=po,
                supplier=selling_company.partner_id,
            )
            po_line_vals.update({
                'analytic_tag_ids': [(6, 0, [sale_line.analytic_tag_ids.ids])]
            })
            PurchaseOrderLine.create(po_line_vals)
        po.button_confirm()
        return po

    @api.multi
    def _prepare_purchase_order(self, selling_partner, selling_company, receiving_company):
        fpos = self.env['account.fiscal.position'] \
            .with_context(force_company=selling_company.id).get_fiscal_position(selling_partner.id)

        warehouse = (
            receiving_company.warehouse_id and
            receiving_company.warehouse_id.company_id.id == receiving_company.id and
            receiving_company.warehouse_id or False)
        if not warehouse:
            raise UserError(_(
                'Configure correct warehouse for company (%s) in '
                'Menu: Settings/users/companies' % (receiving_company.name)))

        return {
            'partner_id': selling_partner.id,
            'picking_type_id': warehouse.in_type_id.id,
            'company_id': receiving_company.id,
            'currency_id': self.currency_id.id,
            'origin': self.name,
            'payment_term_id': self.payment_term_id.id,
            'date_order': self.date_order,
            'fiscal_position_id': fpos,
            'auto_sale_order_id': self.id,
        }

    @api.multi
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom, price_unit, po, supplier):
        procurement_uom_po_qty = product_uom._compute_quantity(product_qty, product_id.uom_po_id)
        seller = product_id._select_seller(
            partner_id=supplier,
            quantity=procurement_uom_po_qty,
            date=po.date_order and po.date_order[:10],
            uom_id=product_id.uom_po_id)

        taxes = product_id.supplier_taxes_id
        fpos = po.fiscal_position_id
        taxes_id = fpos.map_tax(taxes) if fpos else taxes
        if taxes_id:
            taxes_id = taxes_id.filtered(lambda x: x.company_id.id == po.company_id.id)

        product_lang = product_id.with_context({
            'lang': supplier.lang,
            'partner_id': supplier.id,
        })
        name = product_lang.display_name
        if product_lang.description_purchase:
            name += '\n' + product_lang.description_purchase

        date_planned = self.env['purchase.order.line']._get_date_planned(seller, po=po).strftime(DEFAULT_SERVER_DATETIME_FORMAT)

        return {
            'name': name,
            'product_qty': procurement_uom_po_qty,
            'product_id': product_id.id,
            'product_uom': product_id.uom_po_id.id,
            'price_unit': price_unit,
            'date_planned': date_planned,
            'taxes_id': [(6, 0, taxes_id.ids)],
            'order_id': po.id,
        }


class SaleOrderLine(models.Model):

    _inherit = "sale.order.line"

    auto_purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Source Purchase Order Line',
        readonly=True,
        copy=False
    )
