# pylint:disable=
# flake8: noqa: E501
# pylama:ignore=E501,C901

from odoo import models, api
from odoo.exceptions import ValidationError


class Picking(models.Model):
    _inherit = "stock.picking"

