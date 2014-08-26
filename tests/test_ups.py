# -*- coding: utf-8 -*-
"""
    test_ups

    Test ups Integration

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from decimal import Decimal
from time import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

import sys
import os
DIR = os.path.abspath(os.path.normpath(
    os.path.join(__file__, '..', '..', '..', '..', '..', 'trytond')
))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction
from trytond.config import CONFIG
CONFIG['data_path'] = '.'


class TestUPS(unittest.TestCase):
    """Test UPS Integration
    """

    def setUp(self):
        trytond.tests.test_tryton.install_module('ups')
        self.sale = POOL.get('sale.sale')
        self.SaleConfig = POOL.get('sale.configuration')
        self.UPSConfiguration = POOL.get('ups.configuration')
        self.UPSService = POOL.get('ups.service')
        self.product = POOL.get('product.product')
        self.uom = POOL.get('product.uom')
        self.account = POOL.get('account.account')
        self.category = POOL.get('product.category')
        self.carrier = POOL.get('carrier')
        self.party = POOL.get('party.party')
        self.party_contact = POOL.get('party.contact_mechanism')
        self.payment_term = POOL.get('account.invoice.payment_term')
        self.country = POOL.get('country.country')
        self.country_subdivision = POOL.get('country.subdivision')
        self.sale = POOL.get('sale.sale')
        self.party_address = POOL.get('party.address')
        self.stock_location = POOL.get('stock.location')
        self.stock_shipment_out = POOL.get('stock.shipment.out')
        self.currency = POOL.get('currency.currency')
        self.company = POOL.get('company.company')
        self.ir_attachment = POOL.get('ir.attachment')
        self.User = POOL.get('res.user')
        self.template = POOL.get('product.template')

        assert 'UPS_LICENSE_NO' in os.environ, \
            "UPS_LICENSE_NO not given. Hint:Use export UPS_LICENSE_NO=<number>"
        assert 'UPS_SHIPPER_NO' in os.environ, \
            "UPS_SHIPPER_NO not given. Hint:Use export UPS_SHIPPER_NO=<number>"
        assert 'UPS_USER_ID' in os.environ, \
            "UPS_USER_ID not given. Hint:Use export UPS_USER_ID=<user_id>"
        assert 'UPS_PASSWORD' in os.environ, \
            "UPS_PASSWORD not given. Hint:Use export UPS_PASSWORD=<password>"

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard"
        )

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_fiscal_year(self, date_=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date_ is None:
            date_ = datetime.utcnow().date()

        if not company:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date_.year,
            'code': 'account.invoice',
            'company': company
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date_.year,
            'start_date': date_ + relativedelta(month=1, day=1),
            'end_date': date_ + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date_.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else None

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def setup_defaults(self):
        """Method to setup defaults
        """
        # Create currency
        currency, = self.currency.create([{
            'name': 'United Stated Dollar',
            'code': 'USD',
            'symbol': 'USD',
        }])
        self.currency.create([{
            'name': 'Indian Rupee',
            'code': 'INR',
            'symbol': 'INR',
        }])

        country_us, = self.country.create([{
            'name': 'United States',
            'code': 'US',
        }])

        subdivision_florida, = self.country_subdivision.create([{
            'name': 'Florida',
            'code': 'US-FL',
            'country': country_us.id,
            'type': 'state'
        }])

        subdivision_california, = self.country_subdivision.create([{
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        }])

        with Transaction().set_context(company=None):
            company_party, = self.party.create([{
                'name': 'Test Party',
                'vat_number': '123456',
                'addresses': [('create', [{
                    'name': 'Amine Khechfe',
                    'street': '247 High Street',
                    'zip': '94301-1041',
                    'city': 'Palo Alto',
                    'country': country_us.id,
                    'subdivision': subdivision_california.id,
                }])]
            }])

        self.ups_service, = self.UPSService.create([{
            'name': 'Next Day Air',
            'code': '01',
        }])

        # UPS Configuration
        self.UPSConfiguration.create([{
            'license_key': os.environ['UPS_LICENSE_NO'],
            'user_id': os.environ['UPS_USER_ID'],
            'password': os.environ['UPS_PASSWORD'],
            'shipper_no': os.environ['UPS_SHIPPER_NO'],
            'is_test': True,
            'uom_system': '01',
        }])
        self.SaleConfig.create([{
            'ups_service_type': self.ups_service.id,
        }])
        self.company, = self.company.create([{
            'party': company_party.id,
            'currency': currency.id,
        }])
        self.party_contact.create([{
            'type': 'phone',
            'value': '8005551212',
            'party': self.company.party.id
        }])

        self.User.write(
            [self.User(USER)], {
                'main_company': self.company.id,
                'company': self.company.id,
            }
        )

        CONTEXT.update(self.User.get_preferences(context_only=True))

        self._create_fiscal_year(company=self.company)
        self._create_coa_minimal(company=self.company)
        self.payment_term, = self._create_payment_term()

        account_revenue, = self.account.search([
            ('kind', '=', 'revenue')
        ])

        # Create product category
        category, = self.category.create([{
            'name': 'Test Category',
        }])

        uom_kg, = self.uom.search([('symbol', '=', 'kg')])
        uom_cm, = self.uom.search([('symbol', '=', 'cm')])
        uom_pound, = self.uom.search([('symbol', '=', 'lb')])

        # Carrier Carrier Product
        carrier_product_template, = self.template.create([{
            'name': 'Test Carrier Product',
            'category': category.id,
            'type': 'service',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'cost_price_method': 'fixed',
            'account_revenue': account_revenue.id,
            'products': [('create', self.template.default_products())]
        }])

        carrier_product = carrier_product_template.products[0]

        # Create product
        template, = self.template.create([{
            'name': 'Test Product',
            'category': category.id,
            'type': 'goods',
            'salable': True,
            'sale_uom': uom_kg,
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom_kg,
            'account_revenue': account_revenue.id,
            'weight': .5,
            'weight_uom': uom_pound.id,
            'products': [('create', self.template.default_products())]
        }])

        self.product = template.products[0]

        # Create party
        carrier_party, = self.party.create([{
            'name': 'Test Party',
        }])

        # Create party
        carrier_party, = self.party.create([{
            'name': 'Test Party',
        }])

        self.carrier, = self.carrier.create([{
            'party': carrier_party.id,
            'carrier_product': carrier_product.id,
            'carrier_cost_method': 'ups',
        }])

        self.sale_party, = self.party.create([{
            'name': 'Test Sale Party',
            'vat_number': '123456',
            'addresses': [('create', [{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'zip': '33137',
                'city': 'Miami, Miami-Dade',
                'country': country_us.id,
                'subdivision': subdivision_florida.id,
            }])]
        }])
        self.party_contact.create([{
            'type': 'phone',
            'value': '8005763279',
            'party': self.sale_party.id
        }])

        self.create_sale(self.sale_party)

    def create_sale(self, party):
        """
        Create and confirm sale order for party with default values.
        """
        with Transaction().set_context(company=self.company.id):

            # Create sale order
            sale, = self.sale.create([{
                'reference': 'S-1001',
                'payment_term': self.payment_term,
                'party': party.id,
                'invoice_address': party.addresses[0].id,
                'shipment_address': party.addresses[0].id,
                'carrier': self.carrier.id,
                'ups_service_type': self.ups_service.id,
                'ups_saturday_delivery': True,
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'quantity': 1,
                        'product': self.product,
                        'unit_price': Decimal('10.00'),
                        'description': 'Test Description1',
                        'unit': self.product.template.default_uom,
                    }]),
                ]
            }])

            self.stock_location.write([sale.warehouse], {
                'address': self.company.party.addresses[0].id,
            })

            # Confirm and process sale order
            self.assertEqual(len(sale.lines), 1)
            self.sale.quote([sale])
            self.assertEqual(len(sale.lines), 2)
            self.sale.confirm([sale])
            self.sale.process([sale])

    def test_0010_generate_ups_labels(self):
        """Test case to generate UPS labels.
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            # Call method to create sale order
            self.setup_defaults()

            shipment, = self.stock_shipment_out.search([])
            self.stock_shipment_out.write([shipment], {
                'code': str(int(time())),
            })

            # Before generating labels
            # There is no tracking number generated
            # And no attachment cerated for labels
            self.assertFalse(shipment.tracking_number)
            attatchment = self.ir_attachment.search([])
            self.assertEqual(len(attatchment), 0)

            # Make shipment in packed state.
            shipment.assign([shipment])
            shipment.pack([shipment])

            with Transaction().set_context(company=self.company.id):
                # Call method to generate labels.
                shipment.make_ups_labels()

            self.assertTrue(shipment.tracking_number)
            self.assertTrue(
                self.ir_attachment.search([
                    ('resource', '=', 'stock.shipment.out,%s' % shipment.id)
                ], count=True) > 0
            )


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.account.tests import test_account
    for test in test_account.suite():
        if test not in suite:
            suite.addTest(test)
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestUPS)
    )
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
