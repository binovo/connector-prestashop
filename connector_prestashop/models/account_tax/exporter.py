# -*- coding: utf-8 -*-
# Copyright 2022 Binovo IT Human Project SL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import changed_by, mapping


class AccountTaxExporter(Component):

    _name = "prestashop.account.tax.exporter"
    _inherit = "prestashop.exporter"
    _apply_on = "prestashop.account.tax"

    def _has_to_skip(self, binding=False):
        """Return True if the export can be skipped"""
        tax = self.binding.odoo_id
        return not tax.amount_type == 'percent' or not tax.type_tax_use == 'sale' if tax else True


class AccountTaxExportMapper(Component):
    _name = "prestashop.account.tax.export.mapper"
    _inherit = "translation.prestashop.export.mapper"
    _apply_on = "prestashop.account.tax"

    direct = [
        ("active", "active"),
    ]

    _translatable_fields = [
        ("name", "name"),
    ]

    @changed_by("amount")
    @mapping
    def tax_rate(self, record):
        # Maximum of 3 decimals in PS for a tax
        rate = float("{:.3f}".format(record.amount))
        return {"rate": rate}
