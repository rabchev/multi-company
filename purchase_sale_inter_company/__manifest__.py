# -*- coding: utf-8 -*-
# Copyright 2013-2014 Odoo SA
# Copyright 2015-2017 Chafique Delli <chafique.delli@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Inter Company Module for Purchase to Sale Order',
    'summary': 'Intercompany PO/SO rules',
    'version': '11.0.1.0.2',
    'category': 'Purchase Management',
    'website': 'http://www.odoo.com',
    'author': 'Odoo SA, Akretion, Odoo Community Association (OCA)',
    'license': 'AGPL-3',
    'installable': True,
    'depends': [
        'sale',
        'purchase',
        'delivery',
        'account_invoice_inter_company',
    ],
    'data': [
        'views/res_company_views.xml',
        'views/purchase_views.xml',
    ],
    'demo': [
        'demo/inter_company_purchase_sale.xml',
    ],
}
