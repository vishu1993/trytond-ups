# -*- coding: utf-8 -*-
"""
    stock.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from decimal import Decimal
import base64
import math

from ups.shipping_package import ShipmentConfirm, ShipmentAccept
from ups.base import PyUPSException
from trytond.model import ModelView, fields
from trytond.wizard import Wizard, StateView, Button
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.rpc import RPC

from .sale import UPS_PACKAGE_TYPES


__metaclass__ = PoolMeta
__all__ = [
    'ShipmentOut', 'StockMove', 'GenerateUPSLabelMessage', 'GenerateUPSLabel'
]

STATES = {
    'readonly': Eval('state') == 'done',
}


class ShipmentOut:
    "Shipment Out"
    __name__ = 'stock.shipment.out'

    is_ups_shipping = fields.Function(
        fields.Boolean('Is Shipping', readonly=True),
        'get_is_ups_shipping'
    )
    ups_service_type = fields.Many2One(
        'ups.service', 'UPS Service Type', states=STATES, depends=['state']
    )
    ups_package_type = fields.Selection(
        UPS_PACKAGE_TYPES, 'Package Content Type', states=STATES,
        depends=['state']
    )
    ups_saturday_delivery = fields.Boolean(
        "Is Saturday Delivery", states=STATES, depends=['state']
    )
    tracking_number = fields.Char('Tracking Number', states=STATES)

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

    def get_is_ups_shipping(self, name):
        """
        Check if shipping is from UPS
        """
        return self.carrier and self.carrier.carrier_cost_method == 'ups'

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        # There can be cases when people might want to use a different
        # shipment carrier at any state except `done`.
        cls.carrier.states = STATES
        cls._error_messages.update({
            'ups_wrong_carrier':
                'Carrier for selected shipment is not UPS',
            'ups_service_type_missing':
                'UPS service type missing.',
            'tracking_number_already_present':
                'Tracking Number is already present for this shipment.',
            'invalid_state': 'Labels can only be generated when the '
                'shipment is in Packed or Done states only',
        })
        cls.__rpc__.update({
            'make_ups_labels': RPC(readonly=False, instantiate=0),
            'get_ups_shipping_cost': RPC(readonly=False, instantiate=0),
        })

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
                lambda move: move.get_weight_for_ups(), self.outgoing_moves
            ))),
            Code=ups_config.weight_uom_code,
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

    def _get_carrier_context(self):
        "Pass shipment in the context"
        context = super(ShipmentOut, self)._get_carrier_context()

        if not self.carrier.carrier_cost_method == 'ups':
            return context

        context = context.copy()
        context['shipment'] = self.id
        return context

    def _get_shipment_confirm_xml(self):
        """
        Return XML of shipment for shipment_confirm
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
                self.delivery_address.to_ups_to_address(),
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
        return shipping_cost, currency.id

    def make_ups_labels(self):
        """
        Make labels for the given shipment

        :return: Tracking number as string
        """
        Attachment = Pool().get('ir.attachment')
        UPSConfiguration = Pool().get('ups.configuration')
        Currency = Pool().get('currency.currency')

        ups_config = UPSConfiguration(1)
        if self.state not in ('packed', 'done'):
            self.raise_user_error('invalid_state')

        if not self.is_ups_shipping:
            self.raise_user_error('ups_wrong_carrier')

        if self.tracking_number:
            self.raise_user_error('tracking_number_already_present')

        shipment_confirm = self._get_shipment_confirm_xml()
        shipment_confirm_instance = ups_config.api_instance(call="confirm")

        try:
            response = shipment_confirm_instance.request(shipment_confirm)
        except PyUPSException, e:
            self.raise_user_error(unicode(e[0]))

        digest = ShipmentConfirm.extract_digest(response)

        shipment_accept = ShipmentAccept.shipment_accept_request_type(digest)

        shipment_accept_instance = ups_config.api_instance(call="accept")

        try:
            response = shipment_accept_instance.request(shipment_accept)
        except PyUPSException, e:
            self.raise_user_error(unicode(e[0]))

        if len(response.ShipmentResults.PackageResults) > 1:
            self.raise_user_error('ups_multiple_packages_not_supported')

        shipment_res = response.ShipmentResults
        package, = shipment_res.PackageResults
        tracking_number = package.TrackingNumber.pyval

        currency, = Currency.search([
            ('code', '=', str(
                shipment_res.ShipmentCharges.TotalCharges.CurrencyCode
            ))
        ])
        shipping_cost = currency.round(Decimal(
            str(shipment_res.ShipmentCharges.TotalCharges.MonetaryValue)
        ))
        self.__class__.write([self], {
            'tracking_number': unicode(tracking_number),
            'cost': shipping_cost,
            'cost_currency': currency,
        })

        Attachment.create([{
            'name': "%s_%s_.png" % (
                tracking_number,
                shipment_res.ShipmentIdentificationNumber.pyval
            ),
            'data': buffer(base64.decodestring(
                package.LabelImage.GraphicImage.pyval
            )),
            'resource': '%s,%s' % (self.__name__, self.id)
        }])
        return tracking_number


class GenerateUPSLabelMessage(ModelView):
    'Generate UPS Labels Message'
    __name__ = 'generate.ups.label.message'

    tracking_number = fields.Char("Tracking number", readonly=True)


class GenerateUPSLabel(Wizard):
    'Generate UPS Labels'
    __name__ = 'generate.ups.label'

    start = StateView(
        'generate.ups.label.message',
        'ups.generate_ups_label_message_view_form',
        [
            Button('Ok', 'end', 'tryton-ok'),
        ]
    )

    def default_start(self, data):
        Shipment = Pool().get('stock.shipment.out')

        try:
            shipment, = Shipment.browse(Transaction().context['active_ids'])
        except ValueError:
            self.raise_user_error(
                'This wizard can be called for only one shipment at a time'
            )

        tracking_number = shipment.make_ups_labels()

        return {'tracking_number': str(tracking_number)}


class StockMove:
    "Stock move"
    __name__ = "stock.move"

    @classmethod
    def __setup__(cls):
        super(StockMove, cls).__setup__()
        cls._error_messages.update({
            'weight_required':
                'Weight for product %s in stock move is missing',
        })

    def get_weight_for_ups(self):
        """
        Returns weight as required for ups
        """
        ProductUom = Pool().get('product.uom')
        UPSConfiguration = Pool().get('ups.configuration')

        ups_config = UPSConfiguration(1)
        if self.product.type == 'service':
            return 0

        if not self.product.weight:
            self.raise_user_error(
                'weight_required',
                error_args=(self.product.name,)
            )

        # Find the quantity in the default uom of the product as the weight
        # is for per unit in that uom
        if self.uom != self.product.default_uom:
            quantity = ProductUom.compute_qty(
                self.uom,
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
