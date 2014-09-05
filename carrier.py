# -*- coding: utf-8 -*-
"""
    carrier

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
from decimal import Decimal

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction

__all__ = ['Carrier', 'UPSService']
__metaclass__ = PoolMeta


class Carrier:
    "Carrier"
    __name__ = 'carrier'

    @classmethod
    def __setup__(cls):
        super(Carrier, cls).__setup__()
        selection = ('ups', 'UPS')
        if selection not in cls.carrier_cost_method.selection:
            cls.carrier_cost_method.selection.append(selection)

    def get_rates(self):
        """
        Return list of tuples as:
            [
                (<display method name>, <rate>, <currency>, <metadata>)
                ...
            ]
        """
        Sale = Pool().get('sale.sale')

        sale = Transaction().context.get('sale')

        if sale:
            return Sale(sale).get_ups_shipping_rates()

        return []

    def get_sale_price(self):
        """Estimates the shipment rate for the current shipment

        The get_sale_price implementation by tryton's carrier module
        returns a tuple of (value, currency_id)

        :returns: A tuple of (value, currency_id which in this case is USD)
        """
        Sale = Pool().get('sale.sale')
        Shipment = Pool().get('stock.shipment.out')

        shipment = Transaction().context.get('shipment')
        sale = Transaction().context.get('sale')

        if Transaction().context.get('ignore_carrier_computation'):
            return Decimal('0'), None
        if not sale and not shipment:
            return Decimal('0'), None

        if self.carrier_cost_method != 'ups':
            return super(Carrier, self).get_sale_price()

        if sale:
            return Sale(sale).get_ups_shipping_cost()

        if shipment:
            return Shipment(shipment).get_ups_shipping_cost()

        return Decimal('0'), None


class UPSService(ModelSQL, ModelView):
    "UPS Service"
    __name__ = 'ups.service'

    active = fields.Boolean('Active', select=True)
    name = fields.Char('Name', required=True, select=True)
    code = fields.Char('Service Code', required=True, select=True)

    @staticmethod
    def default_active():
        return True
