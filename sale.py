# -*- coding: utf-8 -*-
"""
    sale.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from decimal import Decimal
import math

from ups.shipping_package import ShipmentConfirm
from ups.base import PyUPSException
from trytond.model import ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.pyson import Eval

__all__ = ['Configuration', 'Sale', 'SaleLine']
__metaclass__ = PoolMeta


UPS_PACKAGE_TYPES = [
    ('01', 'UPS Letter'),
    ('02', 'Customer Supplied Package'),
    ('03', 'Tube'),
    ('04', 'PAK'),
    ('21', 'UPS Express Box'),
    ('24', 'UPS 25KG Box'),
    ('25', 'UPS 10KG Box'),
    ('30', 'Pallet'),
    ('2a', 'Small Express Box'),
    ('2b', 'Medium Express Box'),
    ('2c', 'Large Express Box'),
]


class Configuration:
    'Sale Configuration'
    __name__ = 'sale.configuration'

    ups_service_type = fields.Many2One(
        'ups.service', 'Default UPS Service Type',
    )
    ups_package_type = fields.Selection(
        UPS_PACKAGE_TYPES, 'Package Content Type'
    )

    @staticmethod
    def default_ups_package_type():
        # This is the default value as specified in UPS doc
        return '02'


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    is_ups_shipping = fields.Function(
        fields.Boolean('Is Shipping', readonly=True),
        'get_is_ups_shipping'
    )
    ups_service_type = fields.Many2One(
        'ups.service', 'UPS Service Type',
    )
    ups_package_type = fields.Selection(
        UPS_PACKAGE_TYPES, 'Package Content Type'
    )
    ups_saturday_delivery = fields.Boolean("Is Saturday Delivery")

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls._buttons.update({
            'update_ups_shipment_cost': {
                'invisible': Eval('state') != 'quotation'
            }
        })

    @staticmethod
    def default_ups_package_type():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.ups_package_type

    @staticmethod
    def default_ups_service_type():
        Config = Pool().get('sale.configuration')
        config = Config(1)
        return config.ups_service_type and config.ups_service_type.id or None

    @staticmethod
    def default_ups_saturday_delivery():
        return False

    def on_change_lines(self):
        """Pass a flag in context which indicates the get_sale_price method
        of ups carrier not to calculate cost on each line change
        """
        with Transaction().set_context({'ignore_carrier_computation': True}):
            return super(Sale, self).on_change_lines()

    def get_is_ups_shipping(self, name):
        """
        Check if shipping is from UPS
        """
        return self.carrier and self.carrier.carrier_cost_method == 'ups'

    def _get_carrier_context(self):
        "Pass sale in the context"
        context = super(Sale, self)._get_carrier_context()

        if not self.carrier.carrier_cost_method == 'ups':
            return context

        context = context.copy()
        context['sale'] = self.id
        return context

    def apply_ups_shipping(self):
        "Add a shipping line to sale for ups"
        Sale = Pool().get('sale.sale')
        Currency = Pool().get('currency.currency')

        if self.is_ups_shipping:
            with Transaction().set_context(self._get_carrier_context()):
                shipment_cost, currency = self.carrier.get_sale_price()
                if not shipment_cost:
                    return
            # Convert the shipping cost to sale currency from USD
            shipment_cost = Currency.compute(
                currency, shipment_cost, self.currency
            )
            Sale.write([self], {
                'lines': [
                    ('create', [{
                        'type': 'line',
                        'product': self.carrier.carrier_product.id,
                        'description': self.ups_service_type.name,
                        'quantity': 1,  # XXX
                        'unit': self.carrier.carrier_product.sale_uom.id,
                        'unit_price': shipment_cost,
                        'shipment_cost': shipment_cost,
                        'amount': shipment_cost,
                        'taxes': [],
                        'sequence': 9999,  # XXX
                    }]),
                    ('delete', [
                        line for line in self.lines if line.shipment_cost
                    ]),
                ]
            })

    @classmethod
    def quote(cls, sales):
        res = super(Sale, cls).quote(sales)
        cls.update_ups_shipment_cost(sales)
        return res

    @classmethod
    @ModelView.button
    def update_ups_shipment_cost(cls, sales):
        "Updates the shipping line with new value if any"
        for sale in sales:
            sale.apply_ups_shipping()

    def _update_ups_shipments(self):
        """
        Update shipments with ups data
        """
        Shipment = Pool().get('stock.shipment.out')

        assert self.is_ups_shipping

        shipments = list(self.shipments)
        Shipment.write(shipments, {
            'ups_service_type': self.ups_service_type.id,
            'ups_package_type': self.ups_package_type,
            'ups_saturday_delivery': self.ups_saturday_delivery,
        })

    def create_shipment(self, shipment_type):
        """
        Create shipments for sale
        """
        shipments = super(Sale, self).create_shipment(shipment_type)
        if shipment_type == 'out' and shipments and self.is_ups_shipping:
            self._update_ups_shipments()
        return shipments

    def _get_ups_packages(self):
        """
        Return UPS Packages XML
        """
        UPSConfiguration = Pool().get('ups.configuration')

        ups_config = UPSConfiguration(1)
        package_type = ShipmentConfirm.packaging_type(
            Code=self.ups_package_type
        )  # FIXME: Support multiple packaging type

        package_weight = ShipmentConfirm.package_weight_type(
            Weight=str(sum(map(
                lambda line: line.get_weight_for_ups(), self.lines
            ))),
            Code=ups_config.uom_system,
            Description=ups_config.weight_uom.name or 'None'
        )
        package_service_options = ShipmentConfirm.package_service_options_type(
            ShipmentConfirm.insured_value_type(MonetaryValue='0')
        )
        package_container = ShipmentConfirm.package_type(
            package_type,
            package_weight,
            package_service_options
        )
        return [package_container]

    def _get_shipment_confirm_xml(self):
        """
        """
        UPSConfiguration = Pool().get('ups.configuration')

        ups_config = UPSConfiguration(1)
        if not self.ups_service_type:
            self.raise_user_error('ups_service_type_missing')

        payment_info_prepaid = \
            ShipmentConfirm.payment_information_prepaid_type(
                AccountNumber=ups_config.shipper_no
            )
        payment_info = ShipmentConfirm.payment_information_type(
            payment_info_prepaid)
        packages = self._get_ups_packages()
        shipment_service = ShipmentConfirm.shipment_service_option_type(
            SaturdayDelivery='1' if self.ups_saturday_delivery
            else 'None'
        )

        shipment_confirm = \
            ShipmentConfirm.shipment_confirm_request_type(
                self.warehouse.address.to_ups_shipper(),
                self.shipment_address.to_ups_to_address(),
                self.warehouse.address.to_ups_from_address(),
                ShipmentConfirm.service_type(Code=self.ups_service_type.code),
                payment_info, shipment_service,
                *packages
            )
        return shipment_confirm

    def get_ups_shipping_cost(self):
        """Returns the calculated shipping cost as sent by ups

        :returns: The shipping cost with currency
        """
        UPSConfiguration = Pool().get('ups.configuration')
        Currency = Pool().get('currency.currency')

        ups_config = UPSConfiguration(1)

        shipment_confirm = self._get_shipment_confirm_xml()
        shipment_confirm_instance = ups_config.api_instance(call="confirm")

        try:
            response = shipment_confirm_instance.request(shipment_confirm)
        except PyUPSException, e:
            self.raise_user_error(unicode(e[0]))

        currency, = Currency.search([
            ('code', '=', str(
                response.ShipmentCharges.TotalCharges.CurrencyCode
            ))
        ])
        shipping_cost = currency.round(Decimal(
            str(response.ShipmentCharges.TotalCharges.MonetaryValue)
        ))
        return shipping_cost, currency


class SaleLine:
    'Sale Line'
    __name__ = 'sale.line'

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        cls._error_messages.update({
            'weight_required': 'Weight is missing on the product %s',
        })

    def get_weight_for_ups(self):
        """
        Returns weight as required for ups.
        """
        ProductUom = Pool().get('product.uom')
        UPSConfiguration = Pool().get('ups.configuration')

        ups_config = UPSConfiguration(1)
        if self.product.type == 'service' or self.quantity <= 0:
            return 0

        if not self.product.weight:
            self.raise_user_error(
                'weight_required',
                error_args=(self.product.name,)
            )

        # Find the quantity in the default uom of the product as the weight
        # is for per unit in that uom
        if self.unit != self.product.default_uom:
            quantity = ProductUom.compute_qty(
                self.unit,
                self.quantity,
                self.product.default_uom
            )
        else:
            quantity = self.quantity

        weight = float(self.product.weight) * quantity

        # Convert weights according to UPS
        if self.product.weight_uom != ups_config.weight_uom:
            weight = ProductUom.compute_qty(
                self.product.weight_uom,
                weight,
                ups_config.weight_uom
            )
        return math.ceil(weight)
