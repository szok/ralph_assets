# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime
import itertools
import random

import factory
from django.template.defaultfilters import slugify
from factory import (
    fuzzy,
    lazy_attribute,
    Sequence,
    SubFactory,
)
from factory.django import DjangoModelFactory
from ralph.account.models import Region
from ralph.cmdb.tests.utils import (
    CIRelationFactory,
    DeviceEnvironmentFactory,
    ServiceCatalogFactory,
)

from ralph_assets import models_assets
from ralph_assets.models_assets import (
    Asset,
    AssetCategory,
    AssetCategoryType,
    AssetManufacturer,
    AssetModel,
    AssetOwner,
    AssetPurpose,
    AssetSource,
    AssetStatus,
    AssetType,
    CoaOemOs,
    DataCenter,
    DeviceInfo,
    OfficeInfo,
    Orientation,
    Rack,
    ServerRoom,
    Service,
    Warehouse,
)
from ralph_assets.models_dc_assets import Accessory, RackAccessory
from ralph_assets.tests.utils import UserFactory

category_code_set = 'ABCDEFGHIJKLMNOPRSTUVWXYZ1234567890'
category_code_combinations = itertools.product(category_code_set, repeat=2)


def unique_str():
    unique_str.counter += 1
    return 'UNIQUE-{0:0>5}'.format(unique_str.counter)
unique_str.counter = 0


def generate_imei(n):
    """Random IMEI generator. This function return random but not unique
    IMEI number. Based on code from http://stackoverflow.com/a/20733310
    """
    def luhn_residue(digits):
        """Luhn algorithm"""
        return sum(sum(divmod(int(d) * (1 + i % 2), 10))
                   for i, d in enumerate(digits[::-1])) % 10

    part = ''.join(str(random.randrange(0, 9)) for _ in range(n - 1))
    res = luhn_residue('{}{}'.format(part, 0))
    return '{}{}'.format(part, -res % 10)


class CoaOemOsFactory(DjangoModelFactory):
    FACTORY_FOR = CoaOemOs

    name = Sequence(lambda n: 'COA OEM OS #%s' % n)


class OfficeInfoFactory(DjangoModelFactory):
    FACTORY_FOR = OfficeInfo

    coa_oem_os = SubFactory(CoaOemOsFactory)
    purpose = AssetPurpose.others

    @lazy_attribute
    def imei(self):
        return generate_imei(15)

    @lazy_attribute
    def license_key(self):
        return str(unique_str())

    @lazy_attribute
    def coa_number(self):
        return str(unique_str())


class ServiceFactory(DjangoModelFactory):
    FACTORY_FOR = Service

    name = Sequence(lambda n: 'Service #%s' % n)


class AssetOwnerFactory(DjangoModelFactory):
    FACTORY_FOR = AssetOwner

    name = Sequence(lambda n: 'Asset owner #%s' % n)


class AssetCategoryFactory(DjangoModelFactory):
    FACTORY_FOR = AssetCategory

    name = Sequence(lambda n: 'Asset category #%s' % n)
    type = AssetCategoryType.back_office

    @lazy_attribute
    def slug(self):
        return slugify(str(self.type) + self.name)

    @lazy_attribute
    def code(self):
        return ''.join(category_code_combinations.next())


class AssetSubCategoryFactory(AssetCategoryFactory):
    parent = SubFactory(AssetCategoryFactory)

    @lazy_attribute
    def slug(self):
        return slugify(str(self.type) + self.name + self.parent.name)


class AssetManufacturerFactory(DjangoModelFactory):
    FACTORY_FOR = AssetManufacturer

    name = Sequence(lambda n: 'Manufacturer #%s' % n)


class AssetModelFactory(DjangoModelFactory):
    FACTORY_FOR = AssetModel

    name = Sequence(lambda n: 'Model #%s' % n)
    type = AssetCategoryType.back_office
    manufacturer = SubFactory(AssetManufacturerFactory)
    category = SubFactory(AssetCategoryFactory)
    height_of_device = 1


class WarehouseFactory(DjangoModelFactory):
    FACTORY_FOR = Warehouse

    name = Sequence(lambda n: 'Warehouse #%s' % n)


class DataCenterFactory(DjangoModelFactory):
    FACTORY_FOR = DataCenter

    name = Sequence(lambda n: 'DataCenter #{}'.format(n))


class ServerRoomFactory(DjangoModelFactory):
    FACTORY_FOR = ServerRoom

    name = Sequence(lambda n: 'Server #{}'.format(n))
    data_center = SubFactory(DataCenterFactory)


class AccessoryFactory(DjangoModelFactory):
    FACTORY_FOR = Accessory

    name = Sequence(lambda n: 'Accessory #{}'.format(n))


class RackFactory(DjangoModelFactory):
    FACTORY_FOR = Rack

    name = Sequence(lambda n: 'Rack #{}'.format(n))
    data_center = SubFactory(DataCenterFactory)
    server_room = SubFactory(ServerRoomFactory)
    visualization_col = fuzzy.FuzzyInteger(1, 10)
    visualization_row = fuzzy.FuzzyInteger(1, 10)


class RackAccessoryFactory(DjangoModelFactory):
    FACTORY_FOR = RackAccessory

    accessory = SubFactory(AccessoryFactory)
    rack = SubFactory(RackFactory)
    position = fuzzy.FuzzyInteger(1, 48)
    remarks = Sequence(lambda n: 'Remarks #{}'.format(n))


class DeviceInfoFactory(DjangoModelFactory):
    FACTORY_FOR = DeviceInfo

    u_level = random.randint(0, 100)
    u_height = random.randint(0, 100)
    rack_old = Sequence(lambda n: 'Rack #%s' % n)
    rack = SubFactory(RackFactory)
    position = fuzzy.FuzzyInteger(1, 48)
    orientation = Orientation.front.id

    @factory.post_generation
    def rack(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return

        if extracted:
            self.rack = extracted
        else:
            server_room = ServerRoomFactory()
            self.data_center = server_room.data_center
            self.server_room = server_room
            self.rack = RackFactory(
                data_center=server_room.data_center, server_room=server_room,
            )


class BudgetInfoFactory(DjangoModelFactory):
    FACTORY_FOR = models_assets.BudgetInfo

    name = Sequence(lambda n: 'Budget info #{}'.format(n))


class OwnerFactory(DjangoModelFactory):
    FACTORY_FOR = models_assets.User

    name = Sequence(lambda n: 'Owner #{}'.format(n))


class AssetFactory(DjangoModelFactory):
    # XXX: DEPRECATED, use: DCAssetFactory, BOAssetFactory
    FACTORY_FOR = Asset

    type = AssetType.data_center
    model = SubFactory(AssetModelFactory)
    status = AssetStatus.new
    source = AssetSource.shipment
    warehouse = SubFactory(WarehouseFactory)
    device_info = SubFactory(DeviceInfoFactory)
    provider = Sequence(lambda n: 'Provider #%s' % n)
    support_period = 24
    support_type = 'standard'

    @lazy_attribute
    def region(self):
        # lazy attr because static fails (it's not accessible during import)
        return Region.get_default_region()

    @lazy_attribute
    def sn(self):
        return unique_str()


class BaseAssetFactory(DjangoModelFactory):
    FACTORY_FOR = Asset

    budget_info = SubFactory(BudgetInfoFactory)
    created = fuzzy.FuzzyNaiveDateTime(
        datetime.datetime(2008, 1, 1),
        force_microsecond=0,
    )
    delivery_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    deprecation_end_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    deprecation_rate = fuzzy.FuzzyInteger(0, 100)
    device_environment = SubFactory(DeviceEnvironmentFactory)
    invoice_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    invoice_no = Sequence(lambda n: 'Invoice no #{}'.format(n))
    loan_end_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    location = Sequence(lambda n: 'location #{}'.format(n))
    model = SubFactory(AssetModelFactory)
    niw = Sequence(lambda n: 'Inventory number #{}'.format(n))
    order_no = Sequence(lambda n: 'Order no #{}'.format(n))
    purchase_order = Sequence(lambda n: 'PURCHASE-{}'.format(n))
    owner = SubFactory(UserFactory)
    price = fuzzy.FuzzyDecimal(0, 100)
    property_of = SubFactory(AssetOwnerFactory)
    production_use_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    provider_order_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    provider = Sequence(lambda n: 'Provider #%s' % n)
    provider_order_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    remarks = Sequence(lambda n: 'Remarks #{}'.format(n))
    request_date = fuzzy.FuzzyDate(datetime.date(2008, 1, 1))
    required_support = False
    service = SubFactory(ServiceCatalogFactory)
    service_name = SubFactory(ServiceFactory)
    # sn exists below, as a lazy_attribute
    source = AssetSource.shipment
    status = AssetStatus.new
    task_url = Sequence(lambda n: 'http://www.url-{}.com/'.format(n))
    user = SubFactory(UserFactory)
    warehouse = SubFactory(WarehouseFactory)

    @lazy_attribute
    def barcode(self):
        return unique_str()

    @lazy_attribute
    def created_by(self):
        return UserFactory().get_profile()

    @lazy_attribute
    def production_year(self):
        return random.randint(1990, 2010)

    @lazy_attribute
    def sn(self):
        return unique_str()

    @factory.post_generation
    def device_environment(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return

        if extracted:
            self.device_environment = extracted
        else:
            if self.service:
                ci_relation = CIRelationFactory(parent=self.service)
                self.device_environment = ci_relation.child

    @factory.post_generation
    def supports(self, create, extracted, **kwargs):
        if not create:
            # Simple build, do nothing.
            return

        if extracted:
            # A list of supports were passed in, use them
            for support in extracted:
                self.supports.add(support)

    @lazy_attribute
    def region(self):
        # lazy attr because static fails (it's not accessible during import)
        return Region.get_default_region()


class DCAssetFactory(BaseAssetFactory):
    type = AssetType.data_center
    device_info = SubFactory(DeviceInfoFactory)

    @lazy_attribute
    def slots(self):
        return random.randint(1, 100)


class BOAssetFactory(BaseAssetFactory):
    type = AssetType.back_office
    hostname = Sequence(lambda n: 'XXXYY{:05}'.format(n))
    office_info = SubFactory(OfficeInfoFactory)


def get_device_info_dict():
    device_info = DeviceInfoFactory()
    device_info_keys = {'orientation', 'position', 'ralph_device_id'}
    device_info_data = {
        k: getattr(device_info, k) for k in device_info_keys
    }
    device_info_data.update({
        'data_center': device_info.data_center.id,
        'rack': device_info.rack.id,
        'server_room': device_info.server_room.id,
    })
    return device_info_data
