# © 2016 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from collections import namedtuple
from unittest import mock

from .common import PrestashopTransactionCase, assert_no_job_delayed, recorder

ExpectedCarrier = namedtuple("ExpectedCarrier", "name company_id")


class TestImportCarrier(PrestashopTransactionCase):
    """Test the import of partner from PrestaShop"""

    def setUp(self):
        super().setUp()
        self.sync_metadata()
        self.base_mapping()
        self.shop_group = self.env["prestashop.shop.group"].search([])
        self.shop = self.env["prestashop.shop"].search([])

    @assert_no_job_delayed
    def test_import_carrier_record(self):
        """Import a carrier"""
        with recorder.use_cassette("test_import_carrier_record_2"):
            self.env["prestashop.delivery.carrier"].import_record(
                self.backend_record, 2
            )
        domain = [
            ("prestashop_id", "=", 2),
            ("backend_id", "=", self.backend_record.id),
        ]
        binding = self.env["prestashop.delivery.carrier"].search(domain)
        binding.ensure_one()

        expected = [
            ExpectedCarrier(
                name="My carrier",
                company_id=self.backend_record.company_id,
            )
        ]

        self.assert_records(expected, binding)
        self.assertEqual("My carrier", binding.name)
