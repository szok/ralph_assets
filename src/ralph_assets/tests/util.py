# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from random import randint

from django.template.defaultfilters import slugify
from ralph.account.models import Region

from ralph_assets import models_assets
from ralph_assets.models_assets import (
    AssetCategory,
    AssetCategoryType,
    AssetModel,
    AssetSource,
    AssetStatus,
    AssetType,
    AssetManufacturer,
    DeviceInfo,
    Warehouse
)

import cgi
import warnings


with warnings.catch_warnings():
    warnings.simplefilter('default', DeprecationWarning)
    warnings.warn('Please use factories from tests.utils.', DeprecationWarning)


DEFAULT_ASSET_DATA = dict(
    manufacturer='Manufacturer1',
    model='Model1',
    power_consumption=100,
    height_of_device='D4',
    warehouse='Warehouse',
    type=AssetType.data_center,
    status=AssetStatus.new,
    source=AssetSource.shipment,
    category='Category1',
    asset_owner='AssetOwner',
    service_name='ServiceName',
)

DEFAULT_BO_VALUE = {
    'license_key': 'bo-license-key',
    'coa_number': 'bo-coa-number',
    'imei': '1' * 15,
    'purpose': models_assets.AssetPurpose.others,
}

SCREEN_ERROR_MESSAGES = dict(
    duplicated_sn_or_bc=cgi.escape((
        'Please correct errors and check both '
        '"serial numbers" and "barcodes" for duplicates'
    ), quote=True),
    duplicated_sn_in_field='There are duplicates in field.',
    contain_white_character="Item can't contain white characters.",
    django_required=(
        "Field can't be empty. Please put the item OR items separated "
        "by new line or comma."
    ),
    count_sn_and_bc="Fields: sn, barcode, imei - require the same count",
    barcode_already_exist='Following items already exist: ',
    empty_items_disallowed="Empty items disallowed, remove it.",
    any_required="SN or BARCODE field is required",
)


def create_manufacturer(name=DEFAULT_ASSET_DATA['manufacturer']):
    manufacturer, created = AssetManufacturer.objects.get_or_create(name=name)
    return manufacturer


def create_warehouse(name=DEFAULT_ASSET_DATA['warehouse']):
    warehouse, created = Warehouse.objects.get_or_create(name=name)
    return warehouse


def create_model(
    name=DEFAULT_ASSET_DATA['model'],
    manufacturer=None,
    category=DEFAULT_ASSET_DATA['category'],
):
    """name = string, manufacturer = string"""
    if not manufacturer:
        manufacturer = create_manufacturer()
    else:
        manufacturer = create_manufacturer(manufacturer)
    model, created = AssetModel.objects.get_or_create(name=name)
    if created:
        model.manufacturer = manufacturer
        if not isinstance(category, AssetCategory):
            try:
                category = AssetCategory.objects.get(pk=category)
            except AssetCategory.DoesNotExist:
                pass
            else:
                model.category = category
        else:
            model.category = category
        model.save()
    return model


def create_device(size=1):
    device = DeviceInfo(size=size)
    device.save()
    return device


def create_asset(sn, **kwargs):
    for field in ['status', 'source', 'type']:
        if field not in kwargs:
            kwargs[field] = DEFAULT_ASSET_DATA[field]
    if not kwargs.get('model'):
        kwargs.update(model=create_model())
    if not kwargs.get('device_info'):
        kwargs.update(device_info=create_device())
    if not kwargs.get('support_period'):
        kwargs.update(support_period=24)
    if not kwargs.get('support_type'):
        kwargs.update(support_type='standard')
    kwargs['region'] = kwargs.get('region', None) or Region.get_default_region()  # noqa
    if not kwargs.get('warehouse'):
        kwargs.update(warehouse=create_warehouse())
    db_object, created = models_assets.Asset.objects.get_or_create(
        sn=sn, defaults=kwargs,
    )
    return db_object


def create_bo_asset(sn, **kwargs):
    """
    Creates asset with office_info data included in kwargs or with defaults
    """
    bo_data = {}
    for bo_field in ['license_key', 'coa_number', 'imei', 'purpose']:
        if bo_field in kwargs:
            bo_value = kwargs.pop(bo_field)
        else:
            bo_value = DEFAULT_BO_VALUE[bo_field]
        bo_data[bo_field] = bo_value
    bo_info = models_assets.OfficeInfo(**bo_data)
    bo_info.save()
    kwargs['office_info'] = bo_info
    db_object = create_asset(sn, **kwargs)
    return db_object


def create_category(type='data_center', name=DEFAULT_ASSET_DATA['category']):
    subcategory_name = 'Subcategory'
    type_name = type
    if type == 'back_office':
        type = AssetCategoryType.back_office
    elif type == 'data_center':
        type = AssetCategoryType.data_center
    category = AssetCategory()
    category.name = name
    category.type = type
    category.slug = slugify(type_name + name)
    category.save()
    subcategory = AssetCategory()
    subcategory.name = subcategory_name
    subcategory.type = type
    subcategory.parent = category
    subcategory.slug = slugify(type_name + category.name + subcategory_name)
    subcategory.save()
    return subcategory


def get_bulk_edit_post_data_part(form_id, *args, **kwargs):
    asset_id = kwargs.get('id')

    model_id = kwargs.get('model')
    if model_id is None:
        model = create_model()
        model_id = model.id

    sn = kwargs.get('sn')
    if sn is None:
        sn = '-'.join([str(randint(1000, 9999)) for i in xrange(4)])

    barcode = kwargs.get('barcode')
    if barcode is None:
        barcode = 'bc-{0}'.format(str(randint(1000, 9999)))

    warehouse = kwargs.get('warehouse')
    if warehouse is None:
        warehouse = create_warehouse()
        warehouse_id = warehouse.id

    def field(field):
        return 'form-{}-{}'.format(form_id, field)

    return {
        field('id'): asset_id,
        field('type'): kwargs.get('type', AssetType.data_center.id),
        field('model'): model_id,
        field('invoice_no'): kwargs.get('invoice_no', 'Invoice No0'),
        field('invoice_date'): kwargs.get('invoice_date', '2014-01-01'),
        field('order_no'): kwargs.get('order_no', 'Order No0'),
        field('sn'): sn,
        field('barcode'): barcode,
        field('support_period'): kwargs.get('support_period', 24),
        field('support_type'): kwargs.get('support_type', 'standard0'),
        field('support_void_reporting'): kwargs.get(
            'support_void_reporting', 'on'
        ),
        field('provider'): kwargs.get('provider', 'Provider 0'),
        field('status'): kwargs.get('status', AssetStatus.in_progress.id),
        field('source'): kwargs.get('source', AssetSource.shipment.id),
        field('ralph_device_id'): kwargs.get('ralph_device_id', ''),
        field('price'): kwargs.get('price', 10),
        field('warehouse'): warehouse_id,
        field('deprecation_rate'): kwargs.get('deprecation_rate', 25),
    }


def get_bulk_edit_post_data(*args, **kwargs):
    post_data = {
        'form-TOTAL_FORMS': u'{0}'.format(len(args)),
        'form-INITIAL_FORMS': u'{0}'.format(len(args)),
        'form-MAX_NUM_FORMS': u'',
    }
    for i, data in enumerate(args):
        post_data.update(get_bulk_edit_post_data_part(form_id=i, **data))
    return post_data


def create_user(username='user', defaults=None):
    if not defaults:
        defaults = {
            'username': username,
            'email': 'user@test.local',
            'is_staff': False,
            'first_name': 'Elmer',
            'last_name': 'Stevens',
        }
    db_object, created = models_assets.User.objects.get_or_create(
        username=username, defaults=defaults,
    )
    return db_object


def create_service(name=DEFAULT_ASSET_DATA['service_name']):
    db_object, created = models_assets.Service.objects.get_or_create(name=name)
    return db_object


def create_asset_owner(name=DEFAULT_ASSET_DATA['asset_owner']):
    db_object, created = models_assets.AssetOwner.objects.get_or_create(
        name=name,
    )
    return db_object
