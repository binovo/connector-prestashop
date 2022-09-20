# -*- coding: utf-8 -*-
# Copyright 2022 Binovo IT Human Project SL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.component.core import Component


class TaxGroupExporter(Component):

    _name = "prestashop.account.tax.group.exporter"
    _inherit = "prestashop.exporter"
    _apply_on = "prestashop.account.tax.group"


class TaxGroupExportMapper(Component):
    _name = "prestashop.account.tax.group.export.mapper"
    _inherit = "prestashop.export.mapper"
    _apply_on = "prestashop.account.tax.group"

    direct = [
        ("active", "active"),
        ("name", "name"),
    ]
