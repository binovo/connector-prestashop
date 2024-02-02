# © 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from collections import namedtuple
from unittest import mock

from freezegun import freeze_time

from odoo import fields

from .common import PrestashopTransactionCase, assert_no_job_delayed, recorder

ExpectedTemplate = namedtuple("ExpectedProduct", "name list_price")

ExpectedVariant = namedtuple(
    "ExpectedVariant",
    "default_code standard_price product_template_attribute_value_ids",
)


class TestImportProduct(PrestashopTransactionCase):
    """Test the import of partner from PrestaShop"""

    def setUp(self):
        super().setUp()
        self.sync_metadata()
        self.base_mapping()

        self.shop_group = self.env["prestashop.shop.group"].search([])
        self.shop = self.env["prestashop.shop"].search([])

        mock_delay_record = mock.MagicMock()
        self.instance_delay_record = mock_delay_record.return_value
        self.patch_delay_record = mock.patch(
            "odoo.addons.queue_job.models.base.DelayableRecordset",
            new=mock_delay_record,
        )
        self.patch_delay_record.start()

    def tearDown(self):
        super().tearDown()
        self.patch_delay_record.stop()

    def get_ptav(self, from_pav):
        for_pav = [("product_attribute_value_id", "in", from_pav.ids)]
        return self.env["product.template.attribute.value"].search(for_pav)

    @assert_no_job_delayed
    def test_import_product_record(self):
        """Import a product"""
        color_attr = self.env["product.attribute"].search([("name", "=", "Color")])
        conflict_lines = self.env["product.template.attribute.line"].search(
            [("attribute_id", "=", color_attr.id)]
        )
        if conflict_lines:
            conflict_lines.unlink()

        with recorder.use_cassette("test_import_product_template_record_1"):
            self.env["prestashop.product.template"].import_record(
                self.backend_record, 1
            )

        domain = [
            ("prestashop_id", "=", 1),
            ("backend_id", "=", self.backend_record.id),
        ]
        binding = self.env["prestashop.product.template"].search(domain)
        binding.ensure_one()

        expected = [
            ExpectedTemplate(
                name="Faded Short Sleeves T-shirt",
                list_price=16.51,
            )
        ]

        self.assert_records(expected, binding)

        variants = binding.product_variant_ids

        PSValue = self.env["prestashop.product.combination.option.value"]
        value_s = PSValue.search(
            [("backend_id", "=", self.backend_record.id), ("name", "=", "S")]
        ).odoo_id
        value_m = PSValue.search(
            [("backend_id", "=", self.backend_record.id), ("name", "=", "M")]
        ).odoo_id
        value_l = PSValue.search(
            [("backend_id", "=", self.backend_record.id), ("name", "=", "L")]
        ).odoo_id
        value_orange = PSValue.search(
            [("backend_id", "=", self.backend_record.id), ("name", "=", "Orange")]
        ).odoo_id
        value_blue = PSValue.search(
            [("backend_id", "=", self.backend_record.id), ("name", "=", "Blue")]
        ).odoo_id
        s_orange = self.get_ptav(value_s + value_orange)
        s_blue = self.get_ptav(value_s + value_blue)
        m_orange = self.get_ptav(value_m + value_orange)
        m_blue = self.get_ptav(value_m + value_blue)
        l_orange = self.get_ptav(value_l + value_orange)
        l_blue = self.get_ptav(value_l + value_blue)

        expected_variants = [
            ExpectedVariant(
                default_code="1_1",
                standard_price=4.95,
                product_template_attribute_value_ids=s_orange,
            ),
            ExpectedVariant(
                default_code="1_2",
                standard_price=4.95,
                product_template_attribute_value_ids=s_blue,
            ),
            ExpectedVariant(
                default_code="1_3",
                standard_price=4.95,
                product_template_attribute_value_ids=m_orange,
            ),
            ExpectedVariant(
                default_code="1_4",
                standard_price=4.95,
                product_template_attribute_value_ids=m_blue,
            ),
            ExpectedVariant(
                default_code="1_5",
                standard_price=4.95,
                product_template_attribute_value_ids=l_orange,
            ),
            ExpectedVariant(
                default_code="1_6",
                standard_price=4.95,
                product_template_attribute_value_ids=l_blue,
            ),
        ]

        self.assert_records(expected_variants, variants)
