# -*- encoding: utf-8 -*-
"""
    Customizes party address to have address in correct format for UPS API .

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import re

from ups.shipping_package import ShipmentConfirm
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Address']
__metaclass__ = PoolMeta

digits_only_re = re.compile('\D+')


class Address:
    '''
    Address
    '''
    __name__ = "party.address"

    @classmethod
    def __setup__(cls):
        super(Address, cls).__setup__()
        cls._error_messages.update({
            'ups_field_missing':
                '%s is missing in %s.'
        })

    def _get_ups_address_xml(self):
        """
        Return Address XML
        """
        if not all([self.street, self.city, self.country]):
            self.raise_user_error("Street, City and Country are required.")

        if self.country.code in ['US', 'CA'] and not self.subdivision:
            self.raise_user_error(
                "State is required for %s" % self.country.code
            )

        if self.country.code in ['US', 'CA', 'PR'] and not self.zip:
            # If Shipper country is US or Puerto Rico, 5 or 9 digits is
            # required. The character - may be used to separate the first five
            # digits and the last four digits. If the Shipper country is CA,
            # then the postal code is required and must be 6 alphanumeric
            # characters whose format is A#A#A# where A is an uppercase letter
            # and # is a digit. For all other countries the postal code is
            # optional and must be no more than 9 alphanumeric characters long.
            self.raise_user_error("ZIP is required for %s" % self.country.code)

        vals = {
            'AddressLine1': self.street[:35],  # Limit to 35 Char
            'City': self.city[:30],  # Limit 30 Char
            'CountryCode': self.country.code,
        }

        if self.streetbis:
            vals['AddressLine2'] = self.streetbis[:35]  # Limit to 35 char
        if self.subdivision:
            # TODO: Handle Ireland Case
            vals['StateProvinceCode'] = self.subdivision.code[3:]
        if self.zip:
            vals['PostalCode'] = self.zip

        return ShipmentConfirm.address_type(**vals)

    def to_ups_from_address(self):
        '''
        Converts party address to UPS `From Address`.

        :return: Returns instance of FromAddress
        '''
        Company = Pool().get('company.company')

        vals = {}
        if not self.party.phone:
            self.raise_user_error(
                "ups_field_missing",
                error_args=('Phone no.', '"from address"')
            )

        company_id = Transaction().context.get('company')
        if not company_id:
            self.raise_user_error(
                "ups_field_missing",
                error_args=('Company', 'context')
            )

        company_party = Company(company_id).party

        vals = {
            'CompanyName': company_party.name,
            'AttentionName': self.name or self.party.name,
            'TaxIdentificationNumber': company_party.vat_number,
            'PhoneNumber': digits_only_re.sub('', self.party.phone),
        }

        fax = self.party.fax
        if fax:
            vals['FaxNumber'] = fax

        # EMailAddress
        email = self.party.email
        if email:
            vals['EMailAddress'] = email

        return ShipmentConfirm.ship_from_type(
            self._get_ups_address_xml(), **vals)

    def to_ups_to_address(self):
        '''
        Converts party address to UPS `To Address`.

        :return: Returns instance of ToAddress
        '''
        party = self.party

        tax_identification_number = ''
        if party.vat_number:
            tax_identification_number = party.vat_number
        elif hasattr(party, 'tax_exemption_number') and \
                party.tax_exemption_number:
            tax_identification_number = party.tax_exemption_number

        vals = {
            'CompanyName': self.name or party.name,
            'TaxIdentificationNumber': tax_identification_number,
            'AttentionName': self.name or party.name,
        }

        if party.phone:
            vals['PhoneNumber'] = digits_only_re.sub('', party.phone)

        fax = party.fax
        if fax:
            vals['FaxNumber'] = fax

        # EMailAddress
        email = party.email
        if email:
            vals['EMailAddress'] = email

        # TODO: LocationID is optional

        return ShipmentConfirm.ship_to_type(self._get_ups_address_xml(), **vals)

    def to_ups_shipper(self):
        '''
        Converts party address to UPS `Shipper Address`.

        :return: Returns instance of ShipperAddress
        '''
        Company = Pool().get('company.company')
        UPSConfiguration = Pool().get('ups.configuration')

        vals = {}
        if not self.party.phone:
            self.raise_user_error(
                "ups_field_missing",
                error_args=('Phone no.', '"Shipper Address"')
            )

        company_id = Transaction().context.get('company')
        if not company_id:
            self.raise_user_error(
                "ups_field_missing", error_args=('Company', 'context')
            )

        company_party = Company(company_id).party

        vals = {
            'CompanyName': company_party.name,
            'TaxIdentificationNumber': company_party.vat_number,
            'Name': self.name or self.party.name,
            'AttentionName': self.name or self.party.name,
            'PhoneNumber': digits_only_re.sub('', self.party.phone),
            'ShipperNumber': UPSConfiguration(1).shipper_no,
        }

        fax = self.party.fax
        if fax:
            vals['FaxNumber'] = fax

        # EMailAddress
        email = self.party.email
        if email:
            vals['EMailAddress'] = email

        return ShipmentConfirm.shipper_type(
            self._get_ups_address_xml(),
            **vals
        )
