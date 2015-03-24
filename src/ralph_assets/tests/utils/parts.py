# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from factory import (
    fuzzy,
    lazy_attribute,
    Sequence,
    SubFactory,
)
from factory.django import DjangoModelFactory
from ralph.cmdb.tests.utils import (
    DeviceEnvironmentFactory,
    ServiceCatalogFactory,
)

from ralph_assets.models_parts import Part, PartModel, PartModelType
from ralph_assets.tests.utils.assets import (
    AssetFactory,
    AssetType,
    unique_str,
    WarehouseFactory,
)


class PartModelFactory(DjangoModelFactory):
    FACTORY_FOR = PartModel

    model_type = PartModelType.disk
    name = Sequence(lambda n: 'PartModel #%s' % n)


class PartFactory(DjangoModelFactory):
    FACTORY_FOR = Part

    asset = SubFactory(AssetFactory)
    asset_type = AssetType.data_center
    model = SubFactory(PartModelFactory)
    order_no = Sequence(lambda n: 'Order no #{}'.format(n))
    price = fuzzy.FuzzyDecimal(0, 100)
    service = SubFactory(ServiceCatalogFactory)
    part_environment = SubFactory(DeviceEnvironmentFactory)
    warehouse = SubFactory(WarehouseFactory)

    @lazy_attribute
    def sn(self):
        return unique_str()
