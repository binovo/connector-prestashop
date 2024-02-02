# © 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from collections import namedtuple
from unittest import mock

from freezegun import freeze_time

from odoo import fields

from .common import PrestashopTransactionCase, assert_no_job_delayed, recorder

ExpectedPartner = namedtuple(
    "ExpectedPartner",
    "name email newsletter company active shop_group_id shop_id "
    "birthday",
)

ExpectedAddress = namedtuple(
    "ExpectedAddress",
    "name parent_id street street2 city zip country_id phone mobile type",
)


class TestImportPartner(PrestashopTransactionCase):
    """Test the import of partner from PrestaShop"""

    def setUp(self):
        super().setUp()
        self.sync_metadata()
        self.base_mapping()

        self.shop_group = self.env["prestashop.shop.group"].search([])
        self.shop = self.env["prestashop.shop"].search([])

    @assert_no_job_delayed
    def test_import_partner_record(self):
        """Import a partner"""

        delay_record_path = "odoo.addons.queue_job.models.base.DelayableRecordset"
        with recorder.use_cassette("test_import_partner_record_1"), mock.patch(
            delay_record_path
        ) as delay_record_mock:
            self.env["prestashop.res.partner"].import_record(self.backend_record, 1)
            delay_record_instance = delay_record_mock.return_value
            delay_record_instance.import_batch.assert_called_with(
                backend=self.backend_record,
                filters={"filter[id_customer]": "1"},
            )

        domain = [("prestashop_id", "=", 1)]
        partner_bindings = self.env["prestashop.res.partner"].search(domain)
        partner_bindings.ensure_one()

        expected = [
            ExpectedPartner(
                name="John DOE",
                email="pub@prestashop.com",
                newsletter=True,
                company=False,
                active=True,
                shop_group_id=self.shop_group,
                shop_id=self.shop,
                birthday=fields.Date.to_date("1970-01-15"),
            )
        ]
        self.assert_records(expected, partner_bindings)

    @assert_no_job_delayed
    def test_import_partner_address_batch(self):
        delay_record_path = "odoo.addons.queue_job.models.base.DelayableRecordset"
        # execute the batch job directly and replace the record import
        # by a mock (individual import is tested elsewhere)
        cassette_name = "test_import_partner_address_batch"
        with recorder.use_cassette(cassette_name) as cassette, mock.patch(
            delay_record_path
        ) as delay_record_mock:

            self.env["prestashop.address"].import_batch(
                self.backend_record, filters={"filter[id_customer]": "1"}
            )
            expected_query = {
                "limit": ["0,1000"],
                "filter[id_customer]": ["1"],
            }
            self.assertEqual(1, len(cassette.requests))
            self.assertEqual("GET", cassette.requests[0].method)
            self.assertEqual(
                "/api/addresses", self.parse_path(cassette.requests[0].uri)
            )
            query = self.parse_qs(cassette.requests[0].uri)
            self.assertDictEqual(expected_query, query)

            delay_record_instance = delay_record_mock.return_value
            self.assertEqual(2, delay_record_instance.import_record.call_count)

    @assert_no_job_delayed
    def test_import_partner_address_record(self):
        """Import a partner address"""

        partner = self.env["res.partner"].create({"name": "Customer"})
        self.create_binding_no_export(
            "prestashop.res.partner",
            partner.id,
            1,
            shop_group_id=self.shop_group.id,
            shop_id=self.shop.id,
        )
        with recorder.use_cassette("test_import_partner_address_record_1"):
            self.env["prestashop.address"].import_record(self.backend_record, 1)

        domain = [("prestashop_id", "=", 1)]
        address_bindings = self.env["prestashop.address"].search(domain)
        address_bindings.ensure_one()

        expected = [
            ExpectedAddress(
                name="John DOE",
                parent_id=partner,
                street="16, Main street",
                street2="2nd floor",
                city="Paris",
                zip="75002",
                country_id=self.env.ref("base.fr"),
                phone="0102030405",
                mobile=False,
                type="other",
            )
        ]

        self.assert_records(expected, address_bindings)
