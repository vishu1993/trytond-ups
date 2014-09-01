# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool
from party import Address
from carrier import Carrier, UPSService
from sale import Configuration, Sale, SaleLine
from stock import (
    ShipmentOut, StockMove, GenerateUPSLabelMessage, GenerateUPSLabel,
)
from configuration import UPSConfiguration


def register():
    Pool.register(
        Address,
        SaleLine,
        Carrier,
        UPSService,
        UPSConfiguration,
        Configuration,
        Sale,
        StockMove,
        ShipmentOut,
        GenerateUPSLabelMessage,
        module='ups', type_='model'
    )
    Pool.register(
        GenerateUPSLabel,
        module='ups', type_='wizard'
    )
