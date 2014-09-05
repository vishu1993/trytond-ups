# -*- coding: utf-8 -*-
"""
    configuration.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import fields, ModelSingleton, ModelSQL, ModelView
from trytond.pool import Pool
from ups.shipping_package import ShipmentConfirm, ShipmentAccept, ShipmentVoid
from ups.rating_package import RatingService

__all__ = ['UPSConfiguration']


class UPSConfiguration(ModelSingleton, ModelSQL, ModelView):
    """
    Configuration settings for UPS.
    """
    __name__ = 'ups.configuration'

    license_key = fields.Char('UPS License Key', required=True)
    user_id = fields.Char('UPS User Id', required=True)
    password = fields.Char('UPS User Password', required=True)
    shipper_no = fields.Char('UPS Shipper Number', required=True)
    is_test = fields.Boolean('Is Test')
    negotiated_rates = fields.Boolean('Use negotiated rates')
    uom_system = fields.Selection([
        ('00', 'Metric Units Of Measurement'),
        ('01', 'English Units Of Measurement'),
    ], 'UOM System', required=True)
    weight_uom = fields.Function(
        fields.Many2One('product.uom', 'Weight UOM'),
        'get_default_uom'
    )
    weight_uom_code = fields.Function(
        fields.Char('Weight UOM code'), 'get_uom_code'
    )
    length_uom = fields.Function(
        fields.Many2One('product.uom', 'Length UOM'),
        'get_default_uom'
    )

    @staticmethod
    def default_uom_system():
        return '01'

    def get_default_uom(self, name):
        """
        Return default UOM on basis of uom_system
        """
        UOM = Pool().get('product.uom')

        uom_map = {
            '00': {  # Metric
                'weight': 'kg',
                'length': 'cm',
            },
            '01': {  # English
                'weight': 'lb',
                'length': 'in',
            }
        }

        return UOM.search([
            ('symbol', '=', uom_map[self.uom_system][name[:-4]])
        ])[0].id

    def get_uom_code(self, name):
        """
        Return UOM code names depending on the system
        """
        uom_map = {
            '00': {  # Metric
                'weight_uom_code': 'KGS',
                'length_uom_code': 'cm',
            },
            '01': {  # English
                'weight_uom_code': 'LBS',
                'length_uom_code': 'in',
            }
        }

        return uom_map[self.uom_system][name]

    @classmethod
    def __setup__(cls):
        super(UPSConfiguration, cls).__setup__()
        cls._error_messages.update({
            'ups_credentials_required':
                'UPS settings on UPS configuration are incomplete.',
        })

    def api_instance(self, call='confirm', return_xml=False):
        """Return Instance of UPS
        """
        if not all([
            self.license_key,
            self.user_id,
            self.password,
            self.uom_system,
        ]):
            self.raise_user_error('ups_credentials_required')

        if call == 'confirm':
            call_method = ShipmentConfirm
        elif call == 'accept':
            call_method = ShipmentAccept
        elif call == 'void':
            call_method = ShipmentVoid
        elif call == 'rate':
            call_method = RatingService
        else:
            call_method = None

        if call_method:
            return call_method(
                license_no=self.license_key,
                user_id=self.user_id,
                password=self.password,
                sandbox=self.is_test,
                return_xml=return_xml
            )
