# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models

from odoo.addons.component.core import Component


class AccountTaxGroup(models.Model):
    _inherit = "account.tax.group"

    prestashop_bind_ids = fields.One2many(
        comodel_name="prestashop.account.tax.group",
        inverse_name="odoo_id",
        string="PrestaShop Bindings"
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        string="Company",
    )
    tax_ids = fields.One2many(
        comodel_name="account.tax",
        inverse_name="tax_group_id",
        string="Taxes",
    )


class PrestashopAccountTaxGroup(models.Model):
    _name = "prestashop.account.tax.group"
    # Since the prestashop tax group change its ID when updated we could
    # end up with multiple tax group binding with the same backend_id/odoo_id
    # that is why we do not inherit prestashop.odoo.binding
    _inherit = "prestashop.binding"
    _inherits = {"account.tax.group": "odoo_id"}
    _description = "Account Tax Group Prestashop Bindings"

    odoo_id = fields.Many2one(
        comodel_name="account.tax.group",
        string="Tax Group",
        required=True,
        ondelete="cascade",
    )

    def bind_group_taxes(self):
        for tax_group in self:
            if tax_group.prestashop_bind_ids:
                for tax in tax_group.tax_ids.filtered(
                    lambda tx: not tx.prestashop_bind_ids
                        and tx.type_tax_use == "sale" and tx.amount_type == "percent"):
                    tax.prestashop_bind_ids = [(0, 0, {'odoo_id': tax.id, 'backend_id': tax_group.backend_id.id})]
        return True


class TaxGroupAdapter(Component):
    _name = "prestashop.account.tax.group.adapter"
    _inherit = "prestashop.adapter"
    _apply_on = "prestashop.account.tax.group"

    _model_name = "prestashop.account.tax.group"
    _prestashop_model = "tax_rule_groups"
    _export_node_name = "tax_rule_group"
    _export_node_name_res = "tax_rule_group"

    def search(self, filters=None):
        if filters is None:
            filters = {}
        filters["filter[deleted]"] = 0
        return super().search(filters)
