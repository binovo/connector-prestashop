# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import datetime
import logging

from odoo import _, api, models
from odoo.exceptions import ValidationError

from odoo.addons.component.core import Component
from odoo.addons.connector.components.mapper import (
    external_to_m2o,
    mapping,
    only_create,
)
from odoo.addons.queue_job.exception import FailedJobError
from odoo.addons.queue_job.job import identity_exact

_logger = logging.getLogger(__name__)

try:
    import html2text
except ImportError:
    _logger.debug("Cannot import `html2text`")

try:
    from bs4 import BeautifulSoup
except ImportError:
    _logger.debug("Cannot import `bs4`")

try:
    from prestapyt import PrestaShopWebServiceError
except ImportError:
    _logger.debug("Cannot import from `prestapyt`")


class TemplateMapper(Component):
    _name = "prestashop.product.template.mapper"
    _inherit = "prestashop.import.mapper"
    _apply_on = "prestashop.product.template"

    direct = [
        ("wholesale_price", "wholesale_price"),
        (external_to_m2o("id_shop_default"), "default_shop_id"),
        ("link_rewrite", "link_rewrite"),
        ("reference", "reference"),
        ("low_stock_threshold", "low_stock_threshold"),
    ]

    @mapping
    def standard_price(self, record):
        if self.has_combinations(record):
            return {}
        else:
            return {"standard_price": record.get("wholesale_price", 0.0)}

    @mapping
    def weight(self, record):
        if self.has_combinations(record):
            return {}
        else:
            return {"weight": record.get("weight", 0.0)}

    def _apply_taxes(self, tax, price):
        if self.backend_record.taxes_included == tax.price_include:
            return price
        factor_tax = tax.price_include and (1 + tax.amount / 100) or 1.0
        if self.backend_record.taxes_included:
            if not tax.price_include:
                return price / factor_tax
        else:
            if tax.price_include:
                return price * factor_tax

    @mapping
    def list_price(self, record):
        price = 0.0
        tax = self._get_tax_ids(record)
        if record["price"] != "":
            price = float(record["price"])
        price = self._apply_taxes(tax, price)
        return {"list_price": price}

    # obsolete ? TODO clean all tags stuff of create a field to store it
    #    @mapping
    #    def tags_to_text(self, record):
    #        associations = record.get("associations", {})
    #        tags = associations.get("tags", {}).get(
    #            self.backend_record.get_version_ps_key("tag"), []
    #        )
    #        tag_adapter = self.component(
    #            usage="backend.adapter", model_name="_prestashop_product_tag"
    #        )
    #        if not isinstance(tags, list):
    #            tags = [tags]
    #        if tags:
    #            ps_tags = tag_adapter.search(
    #                filters={
    #                    "filter[id]": "[%s]" % "|".join(x["id"] for x in tags),
    #                    "display": "[name]",
    #                }
    #            )
    #            if ps_tags:
    #                return {"tags": ",".join(x["name"] for x in ps_tags)}

    @mapping
    def name(self, record):
        if record["name"]:
            return {"name": record["name"]}
        return {"name": "noname"}

    @mapping
    def date_add(self, record):
        if record["date_add"] == "0000-00-00 00:00:00":
            return {"date_add": datetime.datetime.now()}
        return {"date_add": record["date_add"]}

    @mapping
    def date_upd(self, record):
        if record["date_upd"] == "0000-00-00 00:00:00":
            return {"date_upd": datetime.datetime.now()}
        return {"date_upd": record["date_upd"]}

    def has_combinations(self, record):
        associations = record.get("associations", {})
        combinations = associations.get("combinations", {}).get(
            self.backend_record.get_version_ps_key("combinations")
        )
        return len(combinations or "") != 0

    def _match_combination_odoo_record(self, record):
        # Browse combinations for matching products and find if there
        # is a potential template to be matched
        template = self.env["product.template"]
        associations = record.get("associations", {})
        combinations = associations.get("combinations", {}).get(
            self.backend_record.get_version_ps_key("combinations")
        )
        if len(combinations) == 1:
            # Defensive mode when product have no combinations, force
            # the list mode
            combinations = [combinations]
        for prod in combinations:
            backend_adapter = self.component(
                usage="backend.adapter",
                model_name="prestashop.product.combination",
            )
            variant = backend_adapter.read(int(prod["id"]))
            code = variant.get(self.backend_record.matching_product_ch)
            if not code:
                continue
            if self.backend_record.matching_product_ch == "reference":
                product = self.env["product.product"].search(
                    [("default_code", "=", code)]
                )
                if len(product) > 1:
                    raise ValidationError(
                        _(
                            "Error! Multiple products found with "
                            "combinations reference %s. Maybe consider to "
                            "update you datas"
                        )
                        % code
                    )
                template |= product.product_tmpl_id
            if self.backend_record.matching_product_ch == "barcode":
                product = self.env["product.product"].search([("barcode", "=", code)])
                if len(product) > 1:
                    raise ValidationError(
                        _(
                            "Error! Multiple products found with "
                            "combinations reference %s. Maybe consider to "
                            "update you datas"
                        )
                        % code
                    )
                template |= product.product_tmpl_id
        _logger.debug("template %s" % template)
        if len(template) == 1:
            return {"odoo_id": template.id}
        if len(template) > 1:
            raise ValidationError(
                _(
                    "Error! Multiple templates are found with "
                    "combinations reference. Maybe consider to change "
                    "matching option"
                )
            )

    def _match_template_odoo_record(self, record):
        code = record.get(self.backend_record.matching_product_ch)
        if self.backend_record.matching_product_ch == "reference":
            if code:
                if self._template_code_exists(code):
                    product = self.env["product.template"].search(
                        [("default_code", "=", code)], limit=1
                    )
                    if product:
                        return {"odoo_id": product.id}

        if self.backend_record.matching_product_ch == "barcode":
            if code:
                product = self.env["product.template"].search(
                    [("barcode", "=", code)], limit=1
                )
                if product:
                    return {"odoo_id": product.id}

    @only_create
    @mapping
    def odoo_id(self, record):
        """Will bind the product to an existing one with the same code"""
        #         product = self.env['product.template'].search(
        #             [('default_code', '=', record['reference'])], limit=1)
        #         if product:
        #             return {'odoo_id': product.id}
        if not self.backend_record.matching_product_template:
            return {}
        if self.has_combinations(record):
            return self._match_combination_odoo_record(record)
        else:
            return self._match_template_odoo_record(record)

    def _template_code_exists(self, code):
        model = self.env["product.template"]
        template_binder = self.binder_for("prestashop.product.template")
        template = model.with_context(active_test=False).search(
            [
                ("default_code", "=", code),
                ("company_id", "=", self.backend_record.company_id.id),
            ],
            limit=1,
        )
        return template and not template_binder.to_external(template, wrap=True)

    @mapping
    def default_code(self, record):
        if self.has_combinations(record):
            return {}
        code = record.get("reference")
        if not code:
            code = "backend_%d_product_%s" % (self.backend_record.id, record["id"])
        if (
            not self._template_code_exists(code)
            or self.backend_record.matching_product_ch == "reference"
        ):
            return {"default_code": code}
        i = 1
        current_code = "%s_%d" % (code, i)
        while self._template_code_exists(current_code):
            i += 1
            current_code = "%s_%d" % (code, i)
        return {"default_code": current_code}

    def clear_html_field(self, content):
        html = html2text.HTML2Text()
        html.ignore_images = True
        html.ignore_links = True
        return html.handle(content)

    @staticmethod
    def sanitize_html(content):
        content = BeautifulSoup(content, "html.parser")
        # Prestashop adds both 'lang="fr-ch"' and 'xml:lang="fr-ch"'
        # but Odoo tries to parse the xml for the translation and fails
        # due to the unknow namespace
        for child in content.find_all(lambda tag: tag.has_attr("xml:lang")):
            del child["xml:lang"]
        return content.prettify()

    @mapping
    def descriptions(self, record):
        return {
            "description": self.clear_html_field(record.get("description_short", "")),
            "description_html": self.sanitize_html(record.get("description", "")),
            "description_short_html": self.sanitize_html(
                record.get("description_short", "")
            ),
        }

    @mapping
    def active(self, record):
        return {"always_available": bool(int(record["active"]))}

    @mapping
    def sale_ok(self, record):
        return {"sale_ok": True}

    @mapping
    def purchase_ok(self, record):
        return {"purchase_ok": True}

    @mapping
    def default_image_id(self, record):
        image_id = record.get("id_default_image", {}).get("value", -1)
        return {"default_image_id": image_id}

    @mapping
    def backend_id(self, record):
        return {"backend_id": self.backend_record.id}

    @mapping
    def company_id(self, record):
        return {"company_id": self.backend_record.company_id.id}

    @mapping
    def barcode(self, record):
        if self.has_combinations(record):
            return {}
        barcode = record.get("barcode") or record.get("ean13")
        if barcode in ["", "0"]:
            return {}
        if self.env["barcode.nomenclature"].check_ean(barcode):
            return {"barcode": barcode}
        return {}

    def _get_tax_ids(self, record):
        # if record['id_tax_rules_group'] == '0':
        #     return {}
        binder = self.binder_for("prestashop.account.tax.group")
        tax_group = binder.to_internal(
            record["id_tax_rules_group"],
            unwrap=True,
        )
        tax_ids = tax_group.tax_ids
        if tax_group:
            ERROR = "Tax group `{}` should have one and only one tax, currently have {}"
            assert len(tax_ids) == 1, _(ERROR).format(tax_group.name, len(tax_ids))
        return tax_ids

    @mapping
    def taxes_id(self, record):
        taxes = self._get_tax_ids(record)
        return {"taxes_id": [(6, 0, taxes.ids)]}

    @mapping
    def type(self, record):
        # The same if the product is a virtual one in prestashop.
        if record["type"]["value"] and record["type"]["value"] == "virtual":
            return {"type": "service"}
        return {"type": "product"}

    # TODO FIXME
    #    @mapping
    #    def extras_features(self, record):
    #        mapper = self.component(usage='feature.product.import.mapper')
    #        return mapper.map_record(record).values(**self.options)
    #
    #    @mapping
    #    def extras_manufacturer(self, record):
    #        mapper = self.component(usage='manufacturer.product.import.mapper')
    #        return mapper.map_record(record).values(**self.options)

    @mapping
    def visibility(self, record):
        visibility = record.get("visibility")
        if visibility not in ("both", "catalog", "search"):
            visibility = "none"
        return {"visibility": visibility}

    @mapping
    def on_sale(self, record):
        return {"on_sale": bool(int(record.get("on_sale", False)))}

    @mapping
    def available_for_order(self, record):
        return {"available_for_order": bool(int(record.get("available_for_order", False)))}

    @mapping
    def show_price(self, record):
        return {"show_price": bool(int(record.get("show_price", False)))}

    @mapping
    def low_stock_alert(self, record):
        return {"low_stock_alert": bool(int(record.get("low_stock_alert", False)))}


class FeaturesProductImportMapper(Component):
    # To extend in connector_prestashop_feature module. In this way we
    # dependencies on other modules like product_custom_info
    _name = "prestashop.feature.product.template.mapper"
    _inherit = "prestashop.product.template.mapper"
    _apply_on = "prestashop.product.template"
    _usage = "feature.product.import.mapper"

    @mapping
    def extras_features(self, record):
        return {}


class ManufacturerProductImportMapper(Component):
    # To extend in connector_prestashop_manufacturer module. In this way we
    # dependencies on other modules like product_manufacturer
    _name = "prestashop.manufacturer.product.template.mapper"
    _inherit = "prestashop.product.template.mapper"
    _apply_on = "prestashop.product.template"
    _usage = "manufacturer.product.import.mapper"

    @mapping
    def extras_manufacturer(self, record):
        return {}


class ImportInventory(models.TransientModel):
    # In actual connector version is mandatory use a model
    _name = "_import_stock_available"
    _description = "Dummy Import Inventory Transient model"


class ProductTemplateImporter(Component):
    """Import one translatable record"""

    _name = "prestashop.product.template.importer"
    _inherit = "prestashop.translatable.record.importer"
    _apply_on = "prestashop.product.template"

    _base_mapper = TemplateMapper

    _translatable_fields = {
        "prestashop.product.template": [
            "name",
            "description",
            "link_rewrite",
            "description_short",
            "meta_title",
            "meta_description",
            "meta_keywords",
        ],
    }

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.ConnectorEnvironment`
        """
        super().__init__(environment)

    def _after_import(self, binding):
        super()._after_import(binding)
        self.import_images(binding)
        self.attribute_line(binding)
        self.import_combinations()
        self.deactivate_default_product(binding)

    def deactivate_default_product(self, binding):
        # don't consider product as having variant if they are unactive.
        # don't try to inactive a product if it is already inactive.
        binding = binding.with_context(active_test=True)
        if binding.product_variant_count == 1:
            return
        for product in binding.product_variant_ids:
            if product.product_template_attribute_value_ids:
                continue
            self.env["product.product"].browse(product.id).write({"active": False})

    def attribute_line(self, binding):
        record = self.prestashop_record
        template = binding.odoo_id
        attribute_values = {}
        option_value_binder = self.binder_for(
            "prestashop.product.combination.option.value"
        )

        ps_key = self.backend_record.get_version_ps_key("product_option_value")
        option_values = (
            record.get("associations", {})
            .get("product_option_values", {})
            .get(ps_key, [])
        )
        if not isinstance(option_values, list):
            option_values = [option_values]

        for option_value in option_values:
            value = option_value_binder.to_internal(option_value["id"]).odoo_id
            attr_id = value.attribute_id.id
            value_id = value.id
            if attr_id not in attribute_values:
                attribute_values[attr_id] = []
            attribute_values[attr_id].append(value_id)

        remaining_attr_lines = template.with_context(
            active_test=False
        ).attribute_line_ids
        for attr_id, value_ids in attribute_values.items():
            attr_line = template.with_context(
                active_test=False
            ).attribute_line_ids.filtered(lambda l: l.attribute_id.id == attr_id)
            if attr_line:
                attr_line.write({"value_ids": [(6, 0, value_ids)], "active": True})
                remaining_attr_lines -= attr_line
            else:
                attr_line = self.env["product.template.attribute.line"].create(
                    {
                        "attribute_id": attr_id,
                        "product_tmpl_id": template.id,
                        "value_ids": [(6, 0, value_ids)],
                    }
                )
        if remaining_attr_lines:
            remaining_attr_lines.unlink()

    def _import_combination(self, combination, **kwargs):
        """Import a combination

        Can be overriden for instance to forward arguments to the importer
        """
        # We need to pass the template presta record because we need it
        # for combination mapper
        self.work.parent_presta_record = self.prestashop_record
        if "parent_presta_record" not in self.work._propagate_kwargs:
            self.work._propagate_kwargs.append("parent_presta_record")
        self._import_dependency(
            combination["id"], "prestashop.product.combination", always=True, **kwargs
        )

    def _delay_product_image_variant(self, combinations, **kwargs):
        delayable = self.env["prestashop.product.combination"].with_delay(
            priority=15,
            identity_key=identity_exact,
        )
        delayable.set_product_image_variant(self.backend_record, combinations, **kwargs)

    def import_combinations(self):
        prestashop_record = self._get_prestashop_data()
        associations = prestashop_record.get("associations", {})

        ps_key = self.backend_record.get_version_ps_key("combinations")
        combinations = associations.get("combinations", {}).get(ps_key, [])

        if not isinstance(combinations, list):
            combinations = [combinations]
        if combinations:
            first_exec = combinations.pop(
                combinations.index(
                    {"id": prestashop_record["id_default_combination"]["value"]}
                )
            )
            if first_exec:
                self._import_combination(first_exec)

            for combination in combinations:
                self._import_combination(combination)

            if combinations and associations["images"].get("image"):
                self._delay_product_image_variant([first_exec] + combinations)

    def import_images(self, binding):
        prestashop_record = self._get_prestashop_data()
        associations = prestashop_record.get("associations", {})
        images = associations.get("images", {}).get(
            self.backend_record.get_version_ps_key("image"), {}
        )
        if not isinstance(images, list):
            images = [images]
        for image in images:
            if image.get("id"):
                delayable = self.env["prestashop.product.image"].with_delay(
                    priority=10,
                    identity_key=identity_exact,
                )
                delayable.import_product_image(
                    self.backend_record, prestashop_record["id"], image["id"]
                )

    def _import_dependencies(self):
        self._import_manufacturer()

        record = self.prestashop_record
        ps_key = self.backend_record.get_version_ps_key("product_option_value")
        option_values = (
            record.get("associations", {})
            .get("product_option_values", {})
            .get(ps_key, [])
        )
        if not isinstance(option_values, list):
            option_values = [option_values]
        backend_adapter = self.component(
            usage="backend.adapter",
            model_name="prestashop.product.combination.option.value",
        )
        #        presta_option_values = []
        for option_value in option_values:
            option_value = backend_adapter.read(option_value["id"])
            self._import_dependency(
                option_value["id_attribute_group"],
                "prestashop.product.combination.option",
            )
            self._import_dependency(
                option_value["id"], "prestashop.product.combination.option.value"
            )

    #            presta_option_values.append(option_value)
    #        self.template_attribute_lines(presta_option_values)

    def _import_manufacturer(self):
        self.component(usage="manufacturer.product.importer").import_manufacturer(
            self.prestashop_record.get("id_manufacturer")
        )

    def get_template_model_id(self):
        ir_model = self.env["ir.model"].search(
            [("model", "=", "product.template")], limit=1
        )
        assert len(ir_model) == 1
        return ir_model.id


class ManufacturerProductDependency(Component):
    # To extend in connector_prestashop_feature module. In this way we
    # dependencies on other modules like product_manufacturer
    _name = "prestashop.product.template.manufacturer.importer"
    _inherit = "prestashop.product.template.importer"
    _apply_on = "prestashop.product.template"
    _usage = "manufacturer.product.importer"

    def import_manufacturer(self, manufacturer_id):
        return


class ProductTemplateBatchImporter(Component):
    _name = "prestashop.product.template.batch.importer"
    _inherit = "prestashop.delayed.batch.importer"
    _apply_on = "prestashop.product.template"
