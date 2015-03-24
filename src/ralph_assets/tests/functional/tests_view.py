# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime
import json
import tempfile
import unittest
import uuid
from decimal import Decimal
from urllib import urlencode

from dj.choices import Country
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import resolve, reverse
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from ralph.account.models import Region
from ralph.business.models import Venture
from ralph.cmdb.tests.utils import CIRelationFactory
from ralph.discovery.models_device import Device, DeviceType
from ralph.discovery.tests.util import DeviceFactory
from ralph.ui.tests.global_utils import login_as_su
from ralph.util.tests.utils import (
    RegionFactory,
)

from ralph_assets import models_assets, models_support
from ralph_assets.licences.models import (
    AssetType,
    Licence,
    LicenceAsset,
    LicenceUser,
)
from ralph_assets.forms import DeviceForm
from ralph_assets.models_assets import Asset, SAVE_PRIORITY
from ralph_assets.models_support import Support
from ralph_assets.tests.utils import (
    AjaxClient,
    AttachmentFactory,
    ClientMixin,
    UserFactory,
)
from ralph_assets.tests.unit.tests_other import TestHostnameAssigning
from ralph_assets.tests.utils.assets import (
    AssetFactory,
    AssetManufacturerFactory,
    AssetModelFactory,
    AssetOwnerFactory,
    BOAssetFactory,
    BudgetInfoFactory,
    CoaOemOsFactory,
    DCAssetFactory,
    DeviceInfoFactory,
    ServiceFactory,
    WarehouseFactory,
    unique_str,
    generate_imei,
    get_device_info_dict,
)
from ralph_assets.tests.utils.licences import (
    LicenceAssetFactory,
    LicenceFactory,
    LicenceTypeFactory,
    LicenceUserFactory,
    SoftwareCategoryFactory,
)
from ralph_assets.tests.utils.supports import (
    BOSupportFactory,
    DCSupportFactory,
    SupportTypeFactory,
)
from ralph_assets.views.asset import ChassisBulkEdit


def update(_dict, obj, keys):
    """
    Update *_dict* with *obj*'s values from keys.
    """
    for field_name in keys:
        _dict[field_name] = getattr(obj, field_name)
    return _dict


def get_asset_data():
    """
    Common asset data for DC & BO.

    This can't be a just module dict, becasue these data include factories
    which are not accessible during module import causing error.
    """
    ci_relation = CIRelationFactory()
    return {
        'asset': '',  # required if asset (instead of *part*) is edited
        'barcode': 'barcode1',
        'budget_info': BudgetInfoFactory().id,
        'delivery_date': datetime.date(2013, 1, 7),
        'deprecation_end_date': datetime.date(2013, 7, 25),
        'deprecation_rate': '77.00',
        'device_environment': ci_relation.child.id,
        'invoice_date': datetime.date(2009, 2, 23),
        'invoice_no': 'Invoice no #3',
        'loan_end_date': datetime.date(2013, 12, 29),
        'location': 'location #3',
        'model': AssetModelFactory().id,
        'niw': 'Inventory number #3',
        'order_no': 'Order no #3',
        'owner': UserFactory().id,
        'price': Decimal('43.45'),
        'property_of': AssetOwnerFactory().id,
        'provider': 'Provider #3',
        'provider_order_date': datetime.date(2014, 3, 17),
        'region': Region.get_default_region().id,
        'remarks': 'Remarks #3',
        'request_date': datetime.date(2014, 6, 9),
        'service': ci_relation.parent.id,
        'service_name': ServiceFactory().id,
        'source': models_assets.AssetSource.shipment.id,
        'status': models_assets.AssetStatus.new.id,
        'task_url': 'http://www.url-3.com/',
        'user': UserFactory().id,
        'warehouse': WarehouseFactory().id,
    }


def check_fields(testcase, correct_data, object_to_check):
    """
    Checks if *object_to_check* has the same data as *correct_data*

    :param tc: testcase object
    :param correct_data: list with of tuples: (property_name, expected_value)
    :param object_to_check: dict with requried data
    """
    for prop_name, expected in correct_data:
        object_value = getattr(object_to_check, prop_name)
        try:
            object_value = object_value.id
        except AttributeError:
            pass
        object_value, expected = (
            unicode(object_value), unicode(expected)
        )
        msg = 'Object prop. "{}" is "{}" instead of "{}"'.format(
            prop_name, repr(object_value), repr(expected)
        )
        testcase.assertEqual(object_value, expected, msg)


class TestRegions(object):

    model_factory = None

    def edit_obj_url(self, obj_id):
        raise Exception("Implement it")

    def listing_url(self):
        raise Exception("Implement it")

    def test_show_objects_by_user_region_single(self):
        polish_region = RegionFactory(name='PL')
        self.user.get_profile().region_set.add(polish_region)
        dutch_region = RegionFactory(name='NL')

        [self.model_factory(region=polish_region) for i in xrange(2)]
        [self.model_factory(region=dutch_region) for i in xrange(2)]

        response = self.client.get(self.listing_url())
        self.assertEqual(1, response.context['bob_page'].paginator.num_pages)
        self.assertEqual(2, len(response.context['bob_page'].object_list))

    def test_show_objects_by_user_region_double(self):
        polish_region = RegionFactory(name='PL')
        dutch_region = RegionFactory(name='NL')
        self.user.get_profile().region_set.add(*[polish_region, dutch_region])

        [self.model_factory(region=polish_region) for i in xrange(2)]
        [self.model_factory(region=dutch_region) for i in xrange(2)]

        response = self.client.get(self.listing_url())
        self.assertEqual(1, response.context['bob_page'].paginator.num_pages)
        self.assertEqual(4, len(response.context['bob_page'].object_list))

    def test_404_on_not_granted_region(self):
        polish_region = RegionFactory(name='PL')
        dutch_region = RegionFactory(name='NL')
        self.user.get_profile().region_set.add(polish_region)
        obj = self.model_factory(region=dutch_region)
        response = self.client.get(self.edit_obj_url(obj.id))
        self.assertEqual(response.status_code, 404)


class BaseViewsTest(ClientMixin, TransactionTestCase):
    client_class = AjaxClient

    def setUp(self):
        self.login_as_superuser()
        super(BaseViewsTest, self).setUp()

    def _assert_field_in_form(self, form_url, fields_names):
        check_strings = ('name="{}"'.format(f) for f in fields_names)
        response = self.client.get(form_url)
        for check_string in check_strings:
            self.assertContains(response, check_string)

    def get_object_form_data(self, url, forms_name):
        """
        Gets data from form *form_name* inside context under *url*.
        Useful when, eg. request data for add|edit asset is needed.
        """
        response = self.client.get(url)
        form_data = {}
        for form_name in forms_name:
            form_data.update(response.context[form_name].__dict__['initial'])
        form_data = {k: v for k, v in form_data.iteritems() if v is not None}
        return form_data


class TestDataDisplay(ClientMixin, TestCase):
    """Test check if data from database are displayed on screen"""

    def setUp(self):
        self.login_as_superuser()
        asset_fields = dict(
            barcode='123456789',
            invoice_no='Invoice #1',
            order_no='Order #1',
            invoice_date=datetime.date(2001, 1, 1),
            sn='0000-0000-0000-0000',
        )
        self.asset = AssetFactory(**asset_fields)

    def test_display_data_in_table(self):
        get_search_page = self.client.get('/assets/dc/search')
        self.assertEqual(get_search_page.status_code, 200)

        # Test if data from database are displayed in correct row.
        first_table_row = get_search_page.context_data['bob_page'][0]
        self.assertEqual(self.asset, first_table_row)


class TestDevicesView(BaseViewsTest):
    """
    Parent class for common stuff for Test(DataCenter|BackOffice)DeviceView.
    """

    mode = None
    asset_factory = None

    def edit_obj_url(self, obj_id):
        return reverse('device_edit', args=(self.mode, obj_id))

    def get_add_asset_url(self):
        return reverse('add_device', args=(self.mode,))

    def listing_url(self):
        return reverse('asset_search', args=(self.mode,))

    def setUp(self):
        self.login_as_superuser()
        self._visible_add_form_fields = [
            'asset', 'barcode', 'budget_info', 'category', 'delivery_date',
            'deprecation_end_date', 'deprecation_rate', 'device_environment',
            'invoice_date', 'invoice_no', 'location', 'model', 'niw',
            'order_no', 'owner', 'price', 'property_of', 'provider',
            'provider_order_date', 'remarks', 'request_date', 'service',
            'service_name', 'sn', 'source', 'status', 'task_url', 'type',
            'user', 'warehouse',
        ]
        self._visible_edit_form_fields = self._visible_add_form_fields[:]
        self._visible_edit_form_fields.extend([
            'licences_text', 'supports_text',
        ])

    def _get_add_url(self, type_id=None, mode=None):
        if (not type_id and not mode) or (type_id and mode):
            raise Exception("Pass type_id xor mode")
        if not mode:
            try:
                mode = models_assets.ASSET_TYPE2MODE[type_id],
            except AttributeError:
                raise Exception("Unknown type_id: {}".format(type_id))
        url = reverse('add_device', kwargs={'mode': mode})
        return url

    def get_asset_from_response(self, response):
        asset_id = resolve(response.request['PATH_INFO']).kwargs['asset_id']
        return models_assets.Asset.objects.get(pk=asset_id)

    def get_asset_form_data(self, factory_data=None):
        from ralph_assets import urls
        if not factory_data:
            factory_data = {}
        asset = self.asset_factory(**factory_data)
        url = reverse('device_edit', kwargs={
            'mode': urls.normalize_asset_mode(asset.type.name),
            'asset_id': asset.id,
        })
        form_data = self.get_object_form_data(
            url, ['asset_form', 'additional_info'],
        )
        if asset.device_info:
            asset.device_info.delete()
        elif asset.office_info:
            asset.office_info.delete()
        asset.delete()
        return form_data

    def add_asset_by_form(self, form_data):
        add_asset_url = self._get_add_url(form_data['type'])
        response = self.client.post(add_asset_url, form_data, follow=True)
        self.assertEqual(response.status_code, 200)
        return self.get_asset_from_response(response)

    def prepare_readonly_fields(self, new_asset_data, asset, readonly_fields):
        update(new_asset_data, asset, readonly_fields)

    def _update_with_supports(self, _dict):
        supports = [
            DCSupportFactory().id,
            BOSupportFactory().id,
        ]
        supports_value = '|{}|'.format('|'.join(map(str, supports)))
        _dict.update(dict(supports=supports_value))
        return supports

    def _check_asset_supports(self, asset, expected_supports):
        self.assertEqual(
            len(asset.supports.all()), len(expected_supports),
        )
        del self.new_asset_data['supports']

    def _save_asset_for_hostname_generation(self, extra_data):
        """
        Prepare (BO|DC)asset for further hostname field checks.

        - create asset a1 with hostname=None
        - get edit data from form in context
        - check if a1's hostname is None
        - send save edits request
        - return response object for futher checks
        """
        asset = self.asset_factory(**{
            'hostname': None,
            'status': TestHostnameAssigning.neutral_status,
        })
        url = reverse('device_edit', kwargs={
            'mode': self.mode,
            'asset_id': asset.id,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        edit_data = self.get_asset_form_data()
        edit_data.update(extra_data)
        self.assertIsNone(asset.hostname)
        url = reverse('device_edit', kwargs={
            'mode': self.mode,
            'asset_id': asset.id,
        })
        response = self.client.post(url, edit_data)
        return asset, response

    @override_settings(ASSETS_AUTO_ASSIGN_HOSTNAME=True)
    def _test_hostname_is_assigned(self, extra_data):
        asset, response = self._save_asset_for_hostname_generation(extra_data)
        self.assertRedirects(
            response, response.request['PATH_INFO'], status_code=302,
            target_status_code=200,
        )
        asset = models_assets.Asset.objects.get(pk=asset.id)
        self.assertIsNotNone(asset.hostname)
        return asset

    def update_asset(self, asset_id, **kwargs):
        url = reverse('device_edit', kwargs={
            'mode': self.mode if self.mode else 'back_office',
            'asset_id': asset_id,
        })
        response = self.client.get(url)
        form = response.context['asset_form']
        initial_dict = form.initial
        update_dict = {}
        for fieldset, fields in form.fieldsets.iteritems():
            for field in fields:
                val = initial_dict.get(field, None)
                if val:
                    update_dict[field] = val
        kwargs['region'] = Region.get_default_region().id
        update_dict.update(kwargs)
        response = self.client.post(url, update_dict, follow=True)
        return response, models_assets.Asset.objects.get(id=asset_id)

    def _test_mulitvalues_behaviour(self):
        '''
        - get add device request data d1
        - update d1 with duplicated values for field sn
        - send add device request with data d1
        - assert error about duplicates occured

        - update d1 with unique values for field sn
        - send add device request with data d1
        - assert asset was added
        '''
        request_data = self.get_asset_form_data({
            'region': Region.get_default_region(),
        })
        request_data.update(dict(
            # required, irrelevant data here
            ralph_device_id='',
            hostname='',
        ))
        url = reverse('add_device', kwargs={'mode': self.mode})

        duplicated_sns = ','.join([self.asset_factory.build().sn] * 3)
        request_data['sn'] = duplicated_sns
        response = self.client.post(url, request_data)
        self.assertFormError(
            response, 'asset_form', 'sn', 'There are duplicates in field.',
        )
        unique_sns = ','.join([
            self.asset_factory.build().sn for i in xrange(3)
        ])
        request_data.update(dict(
            sn=unique_sns,
            barcode='1,2,3',
        ))
        request_data['sn'] = unique_sns
        response = self.client.post(url, request_data)
        self.assertEqual(response.status_code, 302)


class TestDataCenterDevicesView(TestDevicesView, TestRegions, BaseViewsTest):

    mode = 'dc'
    model_factory = DCAssetFactory

    def setUp(self):
        super(TestDataCenterDevicesView, self).setUp()
        self.asset_factory = DCAssetFactory
        self.mode = 'dc'
        self.asset_data = get_asset_data()
        self.asset_data.update({
            'type': models_assets.AssetType.data_center.id,
        })
        self.device_info = get_device_info_dict()
        self.additional_fields = DeviceForm.Meta.fields
        self.visible_add_form_fields = self._visible_add_form_fields[:]
        self.visible_add_form_fields.extend(self.additional_fields)
        self.visible_edit_form_fields = self._visible_edit_form_fields[:]
        self.visible_edit_form_fields.extend(self.additional_fields)

    def test_add_device(self):
        """
        Add device with all fields filled.

        - send the full asset's data with post request
        - get saved asset from db
        - asserts all db asset's fields with request's data
        """
        asset_data = self.asset_data.copy()
        asset_data.update({
            'sn': str(uuid.uuid1()),
        })
        device_data = self.device_info.copy()
        device_data['ralph_device_id'] = ''
        request_data = {}
        request_data.update(asset_data)
        request_data.update(device_data)
        url = reverse('add_device', kwargs={'mode': self.mode})
        existing_assets = models_assets.Asset.objects.reverse()
        asset_id = existing_assets[0].id + 1 if existing_assets else 1
        response = self.client.post(url, request_data)
        self.assertRedirects(
            response,
            reverse('device_edit', kwargs={
                'mode': self.mode, 'asset_id': asset_id
            }),
            status_code=302,
            target_status_code=200,
        )
        asset = models_assets.Asset.objects.filter(pk=asset_id).get()
        del asset_data['asset']
        check_fields(self, asset_data.items(), asset)
        device_data['ralph_device_id'] = asset_id
        check_fields(self, device_data.items(), asset.device_info)

    def test_edit_device(self):
        """
        Edit device with all fields filled.

        - generate asset data d1
        - create asset a1
        - send data d1 via edit request to a1
        - get a1 from db
        - assert a1's data is the same as d1 data
        """
        self.new_asset_data = self.asset_data.copy()
        supports = self._update_with_supports(self.new_asset_data)
        new_device_data = self.device_info.copy()
        asset = DCAssetFactory()
        edited_data = {}
        edited_data.update(self.new_asset_data)
        edited_data.update(new_device_data)
        edited_data['ralph_device_id'] = ''
        url = self.edit_obj_url(asset.id)
        response = self.client.post(url, edited_data, follow=True)
        self.assertEqual(response.status_code, 200)
        asset = models_assets.Asset.objects.get(pk=asset.id)
        del self.new_asset_data['asset']
        self._check_asset_supports(asset, supports)
        check_fields(self, self.new_asset_data.items(), asset)
        # disable this check, handling this value is too sophisticated
        del new_device_data['ralph_device_id']
        check_fields(self, new_device_data.items(), asset.device_info)

    def test_hostname_is_assigned(self):
        extra_data = {
            # required data for this test
            'asset': '',  # required button
            'ralph_device_id': '',
            'region': Region.get_default_region().id,
            'slot_no': '',
            'status': str(TestHostnameAssigning.trigger_status.id),
        }
        self._test_hostname_is_assigned(extra_data)

    def test_device_add_form_show_fields(self):
        required_fields = self.visible_add_form_fields[:]
        form_url = reverse('add_device', kwargs={'mode': 'dc'})
        self._assert_field_in_form(form_url, required_fields)

    def test_device_edit_form_show_fields(self):
        required_fields = self.visible_edit_form_fields[:]
        device = DCAssetFactory()
        form_url = reverse(
            'device_edit', kwargs={'mode': 'dc', 'asset_id': device.id},
        )
        self._assert_field_in_form(form_url, required_fields)

    def test_mulitvalues_behaviour(self):
        self._test_mulitvalues_behaviour()

    def test_blacklisted_sns_bahviour(self):
        """
        steps
        - add dc-asset with 3 assets by form
        - second one is blacklisted
        - we got error message
        - assets was not saved
        """
        form_data = self.get_asset_form_data({
            'region': Region.get_default_region(),
        })
        sns = [form_data['sn'], '1234567890']
        form_data.update({
            'sn': ','.join(sns),
            'barcode': ','.join(
                [unique_str() for i in xrange(2)],
            ),
            'ralph_device_id': '',
        })
        add_asset_url = reverse(
            'add_device',
            kwargs={'mode': models_assets.ASSET_TYPE2MODE[form_data['type']]},
        )
        response = self.client.post(add_asset_url, form_data, follow=True)
        error_msg = unicode(response.context['messages']._loaded_messages[0])
        self.assertEqual(
            error_msg,
            'You have provided `sn` which is blacklisted.'
            ' Please use a different one.'
        )
        self.assertFalse(Asset.objects.filter(sn__in=sns).all())

    def test_can_save_correct_region(self):
        valid_region = self.user.get_profile().get_regions()[0]
        form_data = self.get_asset_form_data()
        form_data.update({
            'ralph_device_id': '',
            'region': valid_region.id,
        })
        url = self._get_add_url(mode='dc')
        response = self.client.post(url, form_data, follow=True)
        self.assertEqual(response.status_code, 200)
        asset = Asset.objects.get(sn=form_data['sn'])
        self.assertEqual(asset.region, valid_region)

    def test_cant_save_invalid_region(self):
        invalid_region = RegionFactory()
        form_data = self.get_asset_form_data({'device_info': None})
        form_data.update({
            'ralph_device_id': '',
            'region': invalid_region.id,
        })
        url = self._get_add_url(mode='dc')
        response = self.client.post(url, form_data, follow=True)
        self.assertIn(
            'Select a valid choice.'
            ' That choice is not one of the available choices.',
            response.context['asset_form'].errors['region'],
        )

    def test_shows_correct_regions(self):
        region = RegionFactory()
        self.user.get_profile().region_set.add(region)
        url = self._get_add_url(mode='dc')
        response = self.client.get(url, follow=True)

        correct_choices = [
            (u'', u'---------'),
            (region.id, region.name),
        ]
        for choice, correct_choice in zip(
            response.context['asset_form'].fields['region'].choices,
            correct_choices,
        ):
            self.assertEqual(choice, correct_choice)


class TestBackOfficeDevicesView(TestDevicesView, TestRegions, BaseViewsTest):

    mode = 'back_office'
    model_factory = BOAssetFactory

    def setUp(self):
        super(TestBackOfficeDevicesView, self).setUp()
        self.asset_factory = BOAssetFactory
        self.mode = 'back_office'
        self.asset_data = get_asset_data()
        self.asset_data.update({
            'type': models_assets.AssetType.back_office.id,
        })
        self.office_data = {
            'coa_oem_os': CoaOemOsFactory().id,
            'purpose': models_assets.AssetPurpose.others.id,
            'license_key': str(uuid.uuid1()),
            'imei': generate_imei(15),
            'coa_number': str(uuid.uuid1()),
        }
        self.additional_fields = [
            'budget_info', 'coa_number', 'coa_oem_os', 'license_key',
        ]
        self.visible_add_form_fields = self._visible_add_form_fields[:]
        self.visible_add_form_fields.extend(self.additional_fields)
        self.visible_edit_form_fields = self._visible_edit_form_fields[:]
        self.visible_edit_form_fields.extend(self.additional_fields)

    def test_add_device(self):
        """
        Add device with all fields filled.

        - send the full asset's data with post request
        - get saved asset from db
        - asserts all db asset's fields with request's data
        """
        asset_data = self.asset_data.copy()
        asset_data.update({
            'sn': str(uuid.uuid1()),
        })
        office_data = self.office_data.copy()
        request_data = {}
        request_data.update(asset_data)
        request_data.update(office_data)
        url = reverse('add_device', kwargs={'mode': self.mode})
        existing_assets = models_assets.Asset.objects.reverse()
        asset_id = existing_assets[0].id + 1 if existing_assets else 1
        response = self.client.post(url, request_data)
        self.assertRedirects(
            response,
            reverse('device_edit', kwargs={
                'mode': self.mode, 'asset_id': asset_id
            }),
            status_code=302,
            target_status_code=200,
        )
        asset = models_assets.Asset.objects.filter(pk=asset_id).get()
        del asset_data['asset']
        check_fields(self, asset_data.items(), asset)
        check_fields(self, office_data.items(), asset.office_info)

    def test_edit_device(self):
        """
        Edit device with all fields filled.

        - generate asset data d1
        - create asset a1
        - send data d1 via edit request to a1
        - get a1 from db
        - assert a1's data is the same as d1 data
        """
        self.new_asset_data = self.asset_data.copy()
        self.new_asset_data.update({
            'hostname': 'XXXYY00001',
        })
        supports = self._update_with_supports(self.new_asset_data)
        new_office_data = self.office_data.copy()
        asset = BOAssetFactory()
        edited_data = {}
        edited_data.update(self.new_asset_data)
        edited_data.update(new_office_data)
        url = reverse('device_edit', kwargs={
            'mode': self.mode,
            'asset_id': asset.id,
        })
        response = self.client.post(url, edited_data)
        self.assertRedirects(
            response, url, status_code=302, target_status_code=200,
        )
        asset = models_assets.Asset.objects.get(pk=asset.id)
        del self.new_asset_data['asset']
        self.prepare_readonly_fields(self.new_asset_data, asset, ['hostname'])
        self._check_asset_supports(asset, supports)
        check_fields(self, self.new_asset_data.items(), asset)
        self.assertIsNotNone(asset.hostname)
        check_fields(self, new_office_data.items(), asset.office_info)

    def test_hostname_is_assigned(self):
        extra_data = {
            # required data for this test
            'asset': '',  # required button
            'slot_no': '',
            'status': str(TestHostnameAssigning.trigger_status.id),
            'region': Region.get_default_region().id,
        }
        self._test_hostname_is_assigned(extra_data)

    def test_device_add_form_show_fields(self):
        required_fields = self.visible_add_form_fields[:]
        form_url = reverse('add_device', kwargs={'mode': 'back_office'})
        self._assert_field_in_form(form_url, required_fields)

    def test_device_edit_form_show_fields(self):
        required_fields = self.visible_edit_form_fields[:]
        device = BOAssetFactory()
        form_url = reverse(
            'device_edit', kwargs={
                'mode': 'back_office', 'asset_id': device.id,
            }
        )
        self._assert_field_in_form(form_url, required_fields)

    def test_last_hostname_change_owner(self):
        """Assets user change owner and status and expect new hostname.
        Scenario:
        - user change status and owner in asset
        - again, change status and owner in asset
        - user change status to in progress (this action will by generate
        new hostname respected latest hostname)
        """
        def set_user_country(user, country):
            user.profile.country = country
            user.profile.save()

        user_pl_1 = UserFactory()
        set_user_country(user_pl_1, Country.pl)
        user_pl_2 = UserFactory()
        set_user_country(user_pl_2, Country.pl)
        user_pl_3 = UserFactory()
        set_user_country(user_pl_3, Country.pl)
        user_cz = UserFactory()
        set_user_country(user_cz, Country.cz)
        asset = BOAssetFactory(
            model=AssetModelFactory(category__code='XX'),
            hostname='',
            user=user_pl_1,
            owner=user_pl_1,
            status=models_assets.AssetStatus.new,
        )

        response, asset = self.update_asset(
            asset.id,
            asset=True,
            owner=user_pl_2.id,
            status=models_assets.AssetStatus.in_progress.id,
        )
        self.assertEqual(asset.hostname, 'POLXX00001')

        response, asset = self.update_asset(
            asset.id,
            asset=True,
            owner=user_cz.id,
            status=models_assets.AssetStatus.new.id,
        )
        response, asset = self.update_asset(
            asset.id,
            asset=True,
            status=models_assets.AssetStatus.in_progress.id,
        )
        self.assertEqual(asset.hostname, 'CZEXX00001')

        response, asset = self.update_asset(
            asset.id,
            asset=True,
            owner=user_pl_3.id,
            status=models_assets.AssetStatus.new.id,
        )
        response, asset = self.update_asset(
            asset.id,
            asset=True,
            status=models_assets.AssetStatus.in_progress.id,
        )
        self.assertEqual(asset.hostname, 'POLXX00002')

    def test_mulitvalues_behaviour(self):
        self._test_mulitvalues_behaviour()

    def test_save_without_changes(self):
        """Assets must be the same values after dry save."""
        original_asset = BOAssetFactory(
            force_deprecation=True, region=Region.get_default_region(),
        )
        exclude = [
            'assethistorychange',
            'attachments',
            'cache_version',
            'created',
            'device',
            'licence',
            'licenceasset',
            'licences',
            'modified',
            'parts',
            'source_device',
            'support_period',
            'support_void_reporting',
            'supports',
            'transitionshistory',
        ]

        constant_fields = set(original_asset._meta.get_all_field_names())
        constant_fields.difference_update(exclude)
        response, asset = self.update_asset(
            original_asset.id,
            asset=True,
        )
        for field in constant_fields:
            self.assertEqual(
                getattr(original_asset, field),
                getattr(asset, field),
                'Value of field "{}" is diffrent after save! '
                'Before: {}; after: {}'
                .format(field, getattr(original_asset, field),
                        getattr(asset, field))
            )


class TestLicencesView(TestRegions, BaseViewsTest):
    """This test case concern all licences views."""

    model_factory = LicenceFactory

    def setUp(self):
        super(TestLicencesView, self).setUp()
        self.license_data = {
            'accounting_id': '1',
            'asset_type': models_assets.AssetType.back_office.id,
            # TODO: this field is not saving 'assets':'|{}|'.format(asset.id),
            'budget_info': BudgetInfoFactory().id,
            'invoice_date': datetime.date(2014, 06, 11),
            'invoice_no': 'Invoice no',
            'licence_type': LicenceTypeFactory().id,
            'license_details': 'licence_details',
            'manufacturer': AssetManufacturerFactory().id,
            'niw': 'Inventory number',
            'number_bought': '99',
            'order_no': 'Order no',
            'price': Decimal('100.99'),
            'property_of': AssetOwnerFactory().id,
            'provider': 'Provider',
            'region': Region.get_default_region().id,
            'remarks': 'Additional remarks',
            'service_name': ServiceFactory().id,
            'sn': 'Licence key',
            'software_category': SoftwareCategoryFactory().id,
            'valid_thru': datetime.date(2014, 06, 10),
        }
        self.licence = LicenceFactory()
        self.visible_add_form_fields = [
            'accounting_id', 'asset', 'asset_type', 'budget_info',
            'invoice_date', 'invoice_no', 'licence_type', 'license_details',
            'manufacturer', 'niw', 'number_bought', 'order_no', 'parent',
            'price', 'property_of', 'provider', 'remarks', 'service_name',
            'sn', 'software_category', 'valid_thru',
        ]
        self.visible_edit_form_fields = self.visible_add_form_fields[:]

    def edit_obj_url(self, obj_id):
        return reverse('edit_licence', args=(obj_id,))

    def listing_url(self):
        return reverse('licences_list')

    def update_licence_by_form(self, licence_id, **kwargs):
        url = reverse('edit_licence', kwargs={'licence_id': licence_id})
        response = self.client.get(url)
        form = response.context['form']
        request_data = {}
        for fieldset, fields in form.Meta.fieldset.iteritems():
            for field in fields:
                try:
                    value = form.initial[field]
                except KeyError:
                    pass
                else:
                    request_data[field] = value
        request_data.update(kwargs)
        response = self.client.post(url, request_data, follow=True)
        self.assertEqual(response.context['form'].errors, {})
        return response, Licence.objects.get(id=licence_id)

    def test_add_license(self):
        """
        Add license with all fields filled.

        - send the full license's data with post request
        - get saved license from db
        - asserts all db license's fields with request's data
        """
        request_data = self.license_data.copy()
        response = self.client.post(reverse('add_licence'), request_data)
        self.assertRedirects(
            response, reverse('licences_list'), status_code=302,
            target_status_code=200,
        )
        license = Licence.objects.get(sn=request_data['sn'])
        check_fields(self, request_data.items(), license)

    def test_edit_license(self):
        """
        Edit license with all fields filled.
        - generate license data d1
        - create license l1
        - send data d1 via edit request to l1
        - get l1 from db
        - assert l1's data is the same as d1 data
        """
        new_license_data = self.license_data.copy()
        license = LicenceFactory()
        url = reverse('edit_licence', kwargs={
            'licence_id': license.id,
        })
        response = self.client.post(url, new_license_data)
        self.assertRedirects(
            response, url, status_code=302, target_status_code=200,
        )
        license = Licence.objects.get(pk=license.id)
        check_fields(self, new_license_data.items(), license)

    def test_license_add_form_show_fields(self):
        required_fields = self.visible_add_form_fields[:]
        form_url = reverse('add_licence')
        self._assert_field_in_form(form_url, required_fields)

    def test_license_edit_form_show_fields(self):
        required_fields = self.visible_edit_form_fields[:]
        license = LicenceFactory()
        form_url = reverse(
            'edit_licence', kwargs={'licence_id': license.id},
        )
        self._assert_field_in_form(form_url, required_fields)

    def test_bulk_edit(self):
        num_of_licences = 10
        fields = [
            'accounting_id',
            'asset_type',
            'invoice_date',
            'invoice_no',
            'licence_type',
            'niw',
            'number_bought',
            'order_no',
            'parent',
            'price',
            'property_of',
            'provider',
            'remarks',
            'service_name',
            'sn',
            'software_category',
            'valid_thru',
        ]
        licences = [LicenceFactory() for _ in range(num_of_licences)]
        url = reverse('licence_bulkedit')
        url += '?' + '&'.join(['select={}'.format(obj.pk) for obj in licences])
        response = self.client.get(url, follow=True)

        for key in fields:
            self.assertIn(
                key, response.context['formset'][0].fields.keys()
            )

    def get_license_form_data(self):
        license = LicenceFactory()
        url = reverse('edit_licence', kwargs={
            'licence_id': license.id,
        })
        form_data = self.get_object_form_data(url, ['form'])
        license.delete()
        return form_data

    def test_mulitvalues_behaviour(self):
        """
        - get add license request data d1

        - add licence with duplicated inv.-nb. in data
        - assert error occured

        - edit licence with duplicated sn in data
        - assert licence was added
        """
        request_data = self.get_license_form_data()
        request_data.update(dict(
            # required, irrelevant data here
            parent='',
            sn=','.join([LicenceFactory.build().niw] * 3),
        ))
        url = reverse('add_licence')

        request_data['niw'] = ','.join([LicenceFactory.build().niw] * 3)
        response = self.client.post(url, request_data)
        self.assertFormError(
            response, 'form', 'niw', 'There are duplicates in field.',
        )
        request_data.update(dict(
            niw=','.join([LicenceFactory.build().niw for idx in xrange(3)]),
        ))
        response = self.client.post(url, request_data)
        self.assertEqual(response.status_code, 302)

    def test_licence_count_simple(self):
        licences_per_object = 1
        number_of_users = 5
        number_of_assets = 5
        licences = [LicenceFactory() for idx in xrange(5)]
        for _ in xrange(number_of_assets):
            asset = BOAssetFactory()
            licences[0].assign(asset, licences_per_object)
        for _ in xrange(number_of_users):
            user = UserFactory()
            licences[0].assign(user, licences_per_object)
        url = reverse('count_licences')
        url += '?id={}'.format(licences[0].id)
        response = self.client.ajax_get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content),
            {
                'used_by_users': number_of_users * licences_per_object,
                'used_by_assets': number_of_assets * licences_per_object,
                'total': licences[0].number_bought,
            },
        )

    def test_licence_count_all(self):
        licences_num = 5
        assets_num = 5
        users_num = 5
        licences_per_object = 10
        licences = [LicenceFactory() for idx in xrange(licences_num)]
        total = sum(Licence.objects.values_list(
            'number_bought', flat=True)
        )
        for lic in licences:
            for _ in xrange(assets_num):
                asset = BOAssetFactory()
                lic.assign(asset, licences_per_object)
        for lic in licences:
            for _ in xrange(users_num):
                user = UserFactory()
                lic.assign(user, licences_per_object)
        url = reverse('count_licences')
        response = self.client.ajax_get(url)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            json.loads(response.content),
            {
                'used_by_users': licences_num * assets_num * licences_per_object,  # noqa
                'used_by_assets': licences_num * assets_num * licences_per_object,  # noqa
                'total': total,
            },
        )

    def test_allow_duplicated_sns(self):
        """
        add license by factory with sn sn1
        add by form with sn sn1
        assert 200
        """
        existing_license = LicenceFactory()
        license_data = self.get_license_form_data()
        license_data.update({
            'sn': existing_license.sn,
            'parent': '',
        })
        add_license_url = reverse('add_licence')
        response = self.client.post(
            add_license_url, license_data, follow=True,
        )
        self.assertContains(response, '1 licences added')

    def test_save_without_changes(self):
        """Licence must be the same values after dry save."""
        original_licence = LicenceFactory()
        exclude = set([
            'assets',
            'attachments',
            'cache_version',
            'children',
            'created',
            'licenceasset',
            'licenceuser',
            'modified',
            'users',
        ])
        constant_fields = set(original_licence._meta.get_all_field_names())
        constant_fields.difference_update(exclude)
        response, licence = self.update_licence_by_form(
            original_licence.id,
            **{
                'created': '2014-09-08 13:29:04',  # force correct format
                'parent': '',
            }
        )
        for field in constant_fields:
            self.assertEqual(
                getattr(original_licence, field),
                getattr(licence, field),
                'Value of field "{}" is diffrent after save! '
                'Before: {}; after: {}'
                .format(field, repr(getattr(original_licence, field)),
                        repr(getattr(licence, field)))
            )


class TestSupportsView(TestRegions, BaseViewsTest):
    """This test case concern all supports views."""

    model_factory = DCSupportFactory

    def edit_obj_url(self, obj_id):
        return reverse('edit_support', args=(obj_id,))

    def listing_url(self):
        return reverse('support_list')

    def setUp(self):
        super(TestSupportsView, self).setUp()
        SupportTypeFactory().id
        self.support_data = dict(
            additional_notes="Additional notes",
            # asset='',  # button, skip it
            asset_type=101,
            contract_id='1',
            contract_terms='Contract terms',
            date_from=datetime.date(2014, 06, 17),
            date_to=datetime.date(2014, 06, 18),
            description='Description',
            escalation_path='Escalation path',
            invoice_date=datetime.date(2014, 06, 19),
            invoice_no='Invoice no',
            name='name',
            period_in_months='12',
            price=Decimal('99.99'),
            producer='Producer',
            property_of=AssetOwnerFactory().id,
            region=Region.get_default_region().id,
            serial_no='Serial no',
            sla_type='Sla type',
            status=models_support.SupportStatus.new.id,
            supplier='Supplier',
            support_type=SupportTypeFactory().id,
        )
        self.visible_add_form_fields = [
            'additional_notes', 'asset', 'asset_type', 'contract_id',
            'contract_terms', 'date_from', 'date_to', 'description',
            'escalation_path', 'invoice_date', 'invoice_no', 'name',
            'period_in_months', 'price', 'producer', 'property_of',
            'serial_no', 'sla_type', 'status', 'supplier', 'support_type',
        ]
        self.visible_edit_form_fields = self.visible_add_form_fields[:]
        self.visible_edit_form_fields.extend(['assets'])

    def update_support_by_form(self, support_id, **kwargs):
        url = reverse('edit_support', kwargs={'support_id': support_id})
        response = self.client.get(url)
        form = response.context['form']
        request_data = {}
        for fieldset, fields in form.Meta.fieldset.iteritems():
            for field in fields:
                try:
                    value = form.initial[field]
                except KeyError:
                    pass
                else:
                    request_data[field] = value
        request_data.update(kwargs)
        response = self.client.post(url, request_data, follow=True)
        self.assertEqual(response.context['form'].errors, {})
        return response, models_support.Support.objects.get(id=support_id)

    def _check_supports_assets(self, support, expected_assets):
        self.assertEqual(
            len(support.assets.all()), len(expected_assets),
        )
        del self.new_support_data['assets']

    def _update_with_supports(self, _dict):
        assets = [
            DCAssetFactory().id,
            BOAssetFactory().id,
        ]
        assets_values = '|{}|'.format('|'.join(map(str, assets)))
        _dict.update(dict(assets=assets_values))
        return assets

    def test_add_support(self):
        """
        Add support with all fields filled.

        - send the full support's data with post request
        - get saved support from db
        - asserts all db support's fields with request's data
        """
        request_data = self.support_data.copy()
        response = self.client.post(reverse('add_support'), request_data)
        support = Support.objects.order_by('-id')[0]
        self.assertRedirects(
            response,
            reverse('edit_support', kwargs={'support_id': support.id}),
            status_code=302,
            target_status_code=200,
        )
        support = models_support.Support.objects.reverse()[0]
        check_fields(self, request_data.items(), support)

    def test_edit_support(self):
        """
        Edit support with all fields filled.
        - generate support data
        - create support
        - send data via edit request to
        - get from db
        - assert data is the same as data
        """

        self.new_support_data = self.support_data.copy()
        assets = self._update_with_supports(self.new_support_data)
        support = BOSupportFactory()
        url = reverse('edit_support', kwargs={
            'support_id': support.id,
        })
        response = self.client.post(url, self.new_support_data)
        self.assertRedirects(
            response, url, status_code=302, target_status_code=200,
        )
        support = models_support.Support.objects.get(pk=support.id)
        self._check_supports_assets(support, assets)
        check_fields(self, self.new_support_data.items(), support)

    def test_license_add_form_show_fields(self):
        required_fields = self.visible_add_form_fields[:]
        form_url = reverse('add_support')
        self._assert_field_in_form(form_url, required_fields)

    def test_license_edit_form_show_fields(self):
        required_fields = self.visible_edit_form_fields[:]
        test_data = (
            ('dc', DCSupportFactory()),
            ('back_office', BOSupportFactory()),
        )
        for mode, support in test_data:
            form_url = reverse(
                'edit_support',
                kwargs={'support_id': support.id},
            )
            self._assert_field_in_form(form_url, required_fields)

    def test_save_without_changes(self):
        """Support must be the same values after dry save."""
        original_support = DCSupportFactory()
        exclude = set([
            'attachments',
            'assets',
            'created',
            'cache_version',
            'modified',
        ])
        constant_fields = set(original_support._meta.get_all_field_names())
        constant_fields.difference_update(exclude)
        response, support = self.update_support_by_form(
            original_support.id,
            **{
                'created': '2014-09-08 13:29:04',  # force correct format
            }
        )
        for field in constant_fields:
            self.assertEqual(
                getattr(original_support, field),
                getattr(support, field),
                'Value of field "{}" is diffrent after save! '
                'Before: {}; after: {}'
                .format(field, getattr(original_support, field),
                        getattr(support, field))
            )


class TestAttachments(BaseViewsTest):
    """This test case concern all attachments views."""

    def test_cant_add_empty_attachment(self):
        """
        create asset a1
        send post with blank file
        assert that message about blank error exists
        """
        parent = BOAssetFactory()
        add_attachment_url = reverse('add_attachment', kwargs={
            'parent': 'asset',
        })
        full_url = "{}?{}".format(
            add_attachment_url,
            urlencode({'select': obj.id for obj in [parent]}),
        )
        with tempfile.TemporaryFile() as test_file:
            data = {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "form-MAX_NUM_FORMS": 1,
                "form-0-file": test_file,
            }
            response = self.client.post(full_url, data, follow=True)
        self.assertIn(
            'The submitted file is empty.',
            response.context['formset'][0].errors['file'],
        )

    def test_add_bo_asset_attachment(self):
        add_attachment_url = reverse('add_attachment', kwargs={
            'parent': 'asset',
        })
        self.add_attachment(BOAssetFactory(), add_attachment_url)

    def test_add_dc_asset_attachment(self):
        add_attachment_url = reverse('add_attachment', kwargs={
            'parent': 'asset',
        })
        self.add_attachment(DCAssetFactory(), add_attachment_url)

    def test_add_license_attachment(self):
        add_attachment_url = reverse('add_attachment', kwargs={
            'parent': 'license',
        })
        self.add_attachment(LicenceFactory(), add_attachment_url)

    def test_add_support_attachment(self):
        add_attachment_url = reverse('add_attachment', kwargs={
            'parent': 'support',
        })
        self.add_attachment(
            BOSupportFactory(),
            add_attachment_url,
        )

    def add_attachment(self, parent, add_attachment_url):
        """
        Checks if attachment can be added.
        """
        file_content = 'anything'
        full_url = "{}?{}".format(
            add_attachment_url,
            urlencode({'select': obj.id for obj in [parent]}),
        )

        asset = parent.__class__.objects.get(pk=parent.id)
        self.assertEqual(asset.attachments.count(), 0)

        with tempfile.TemporaryFile() as test_file:
            saved_filename = test_file.name
            test_file.write(file_content)
            test_file.seek(0)
            data = {
                "form-TOTAL_FORMS": 1,
                "form-INITIAL_FORMS": 1,
                "form-MAX_NUM_FORMS": 1,
                "form-0-file": test_file,
            }
            response = self.client.post(full_url, data, follow=True)

        self.assertEqual(response.status_code, 200)
        asset = parent.__class__.objects.get(pk=parent.id)
        self.assertEqual(asset.attachments.count(), 1)
        attachment = asset.attachments.all()[0]
        self.assertEqual(attachment.original_filename, saved_filename)
        with attachment.file as attachment_file:
            self.assertEqual(attachment_file.read(), file_content)

    def test_delete_one_bo_asset_attachment(self):
        self.delete_attachment_check(
            parent_name='asset',
            parents=[BOAssetFactory()],
            delete_type='from_one',
        )

    def test_delete_one_bo_licence_attachment(self):
        self.delete_attachment_check(
            parent_name='license',
            parents=[LicenceFactory()],
            delete_type='from_one',
        )

    def test_delete_one_bo_support_attachment(self):
        self.delete_attachment_check(
            parent_name='support',
            parents=[BOSupportFactory()],
            delete_type='from_one',
        )

    def test_delete_all_bo_asset_attachment(self):
        self.delete_attachment_check(
            parent_name='asset',
            parents=[BOAssetFactory(), BOAssetFactory(), BOAssetFactory()],
            delete_type='from_all',
        )

    def test_delete_all_bo_licence_attachment(self):
        self.delete_attachment_check(
            parent_name='license',
            parents=[LicenceFactory(), LicenceFactory(), LicenceFactory()],
            delete_type='from_all',
        )

    def test_delete_all_bo_support_attachment(self):
        self.delete_attachment_check(
            parent_name='support',
            parents=[
                BOSupportFactory(), BOSupportFactory(), BOSupportFactory(),
            ],
            delete_type='from_all',
        )

    def test_delete_one_dc_asset_attachment(self):
        self.delete_attachment_check(
            parent_name='asset',
            parents=[DCAssetFactory()],
            delete_type='from_one',
        )

    def test_delete_one_dc_licence_attachment(self):
        self.delete_attachment_check(
            parent_name='license',
            parents=[LicenceFactory()],
            delete_type='from_one',
        )

    def test_delete_one_dc_support_attachment(self):
        self.delete_attachment_check(
            parent_name='support',
            parents=[DCSupportFactory()],
            delete_type='from_one',
        )

    def test_delete_all_dc_asset_attachment(self):
        self.delete_attachment_check(
            parent_name='asset',
            parents=[DCAssetFactory(), DCAssetFactory(), DCAssetFactory()],
            delete_type='from_all',
        )

    def test_delete_all_dc_licence_attachment(self):
        self.delete_attachment_check(
            parent_name='license',
            parents=[LicenceFactory(), LicenceFactory(), LicenceFactory()],
            delete_type='from_all',
        )

    def test_delete_all_dc_support_attachment(self):
        self.delete_attachment_check(
            parent_name='support',
            parents=[
                DCSupportFactory(), DCSupportFactory(), DCSupportFactory(),
            ],
            delete_type='from_all',
        )

    def delete_attachment_check(self, parent_name, parents, delete_type):
        attachment = AttachmentFactory()
        for parent in parents:
            parent.attachments.add(attachment)
            parent.save()

        parent = parents[0]  # each one is suitable, so take the first
        full_url = reverse('delete_attachment', kwargs={
            'parent': parent_name,
        })
        data = {
            'parent_id': parent.id,
            'attachment_id': attachment.id,
            'delete_type': delete_type,
        }

        for parent in parents:
            self.assertIn(attachment, parent.attachments.all())
        response = self.client.post(full_url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        for parent in parents:
            self.assertNotIn(
                attachment,
                parent.attachments.filter(pk=attachment.id),
            )


class TestImport(ClientMixin, TestCase):
    def setUp(self):
        self.login_as_superuser()
        self.url = reverse('xls_upload')

    def _update_asset_by_csv(self, asset, field, value):
        self.client.get(self.url)
        csv_data = '"id","{}"\n"{}","{}"'.format(field, asset.id, value)

        step1_post = {
            'upload-asset_type': AssetType.back_office.id,
            'upload-model': 'ralph_assets.asset',
            'upload-file': SimpleUploadedFile('test.csv', csv_data),
            'xls_upload_view-current_step': 'upload',
        }
        response = self.client.post(self.url, step1_post)
        self.assertContains(response, 'column_choice')
        self.assertContains(response, 'step 2/3')

        step2_post = {
            'column_choice-%s' % field: field,
            'xls_upload_view-current_step': 'column_choice',
        }
        response = self.client.post(self.url, step2_post)
        self.assertContains(response, 'step 3/3')

        step3_post = {
            'xls_upload_view-current_step': 'confirm',
        }
        response = self.client.post(self.url, step3_post)
        self.assertContains(response, 'Import done')

    def test_import_csv_asset_back_office_update(self):
        self.client.get(self.url)
        asset = BOAssetFactory()

        for field in [
            'barcode', 'invoice_no', 'order_no', 'sn', 'remarks', 'niw'
        ]:
            new_value = str(uuid.uuid1())
            self._update_asset_by_csv(asset, field, new_value)
            updated_asset = models_assets.Asset.objects.get(id=asset.id)
            self.assertEqual(
                getattr(updated_asset, field), new_value
            )


class TestColumnsInSearch(BaseViewsTest):

    def get_cols_by_mode(self, bob_cols, mode):
        mode_cols = set()
        for col in bob_cols:
            if not col.bob_tag:
                continue
            if (col.show_conditions is True) or (
                isinstance(col.show_conditions, tuple) and
                col.show_conditions[1] == mode
            ):
                mode_cols.add(col.header_name)
        return mode_cols

    def check_cols_presence(self, search_url, correct_col_names, mode):
        """
        Checks if bob table has all required columns.
        :parma search_url: url where bob table occures,
        :parma correct_col_names: sequence of expected column names,
        :parma mode: filtering mode comapared with
            bob_table.col.show_conditions, which is 'dc' or 'back_office'
        """
        response = self.client.get(search_url)
        self.assertEqual(response.status_code, 200)
        if mode:
            found_cols = self.get_cols_by_mode(
                response.context_data['columns'], mode
            )
        else:
            found_cols = [
                unicode(col.header_name)
                for col in response.context_data['columns']
            ]
        self.assertEqual(len(found_cols), len(correct_col_names))
        for correct_field in correct_col_names:
            self.assertIn(correct_field, found_cols)

    def test_bo_cols_presence(self):
        BOAssetFactory()
        correct_col_names = set([
            'Additional remarks', 'Barcode', 'Category', 'Dropdown',
            'Hostname', 'IMEI', 'Invoice date', 'Invoice no.', 'Manufacturer',
            'Model', 'Property of', 'SN', 'Service name', 'Status', 'Type',
            'User', 'Warehouse', 'Created',
        ])
        mode = 'back_office'
        search_url = reverse('asset_search', kwargs={'mode': mode})
        self.check_cols_presence(search_url, correct_col_names, mode)

    def test_dc_cols_presence(self):
        DCAssetFactory()
        correct_col_names = set([
            'Barcode', 'Discovered', 'Dropdown', 'Invoice date',
            'Invoice no.', 'Model', 'Order no.', 'Price', 'SN', 'Status',
            'Type', 'Venture', 'Warehouse',
        ])
        mode = 'dc'
        search_url = reverse('asset_search', kwargs={'mode': mode})
        self.check_cols_presence(search_url, correct_col_names, mode)

    def test_license_cols_presence(self):
        LicenceFactory()
        correct_col_names = set([
            'Dropdown', 'Inventory number', 'Invoice date', 'Invoice no.',
            'Licence Type', 'Manufacturer', 'Number of purchased items',
            'Property of', 'Software Category', 'Type', 'Used', 'Valid thru',
            'Created',
        ])
        search_url = reverse('licences_list')
        self.check_cols_presence(search_url, correct_col_names, mode=None)

    def test_supports_cols_presence(self):
        DCSupportFactory()
        correct_col_names = set([
            'Dropdown', 'Type', 'Contract id', 'Name', 'Date from', 'Date to',
            'Price', 'Created',
        ])
        search_url = reverse('support_list')
        self.check_cols_presence(search_url, correct_col_names, mode=None)


class TestSyncFieldMixin(TestDevicesView):
    """Whether this the synced field will saved in Assets and Ralph Core"""

    def setUp(self):
        self.client = login_as_su()
        self.asset_factory = DCAssetFactory

    def create_device(self):
        venture = Venture(name='TestVenture', symbol='testventure')
        venture.save()
        Device.create(
            sn='000000001',
            model_name='test_model',
            model_type=DeviceType.unknown,
            priority=SAVE_PRIORITY,
            venture=venture,
            name='test_device',
        )
        return Device.objects.get(sn='000000001')

    def test_sync_field_in_asset_and_core_on_add_form(self):
        """Asset has assigned Ralph device, fields will be saved twice"""
        ci_relation = CIRelationFactory()
        device_environment = ci_relation.child
        service = ci_relation.parent
        data = self.get_asset_form_data()
        device = self.create_device()
        data.update({
            'device_environment': device_environment.id,
            'ralph_device_id': device.id,
            'region': Region.get_default_region().id,
            'service': service.id,
        })

        url = reverse('add_device', kwargs={'mode': 'dc'})
        self.client.post(url, data, follow=True)

        asset = Asset.objects.all()[0]
        device = Device.objects.get(pk=device.id)

        self.assertNotEqual(device.service, None)
        self.assertEqual(device.service, asset.service)
        self.assertNotEqual(asset.device_environment, None)
        self.assertEqual(device.device_environment, asset.device_environment)

    def test_sync_field_on_edit_asset(self):
        """Asset created without Ralph device.
        Fields sync when edit form saved."""
        ci_relation = CIRelationFactory()
        device_environment = ci_relation.child
        service = ci_relation.parent
        asset = DCAssetFactory()
        asset.device_info.ralph_device_id = None
        asset.device_info.save()

        self.assertEqual(asset.device_info.ralph_device_id, None)

        device = self.create_device()

        url = reverse(
            'device_edit', kwargs={'mode': 'dc', 'asset_id': asset.id},
        )
        data = self.get_object_form_data(url, ['asset_form', 'additional_info'])  # noqa
        data.update({
            'asset': 1,
            'device_environment': device_environment.id,
            'ralph_device_id': device.id,
            'region': Region.get_default_region().id,
            'service': service.id,
        })
        self.client.post(url, data, follow=True)

        asset = Asset.objects.all()[0]
        device = Device.objects.get(pk=device.id)

        self.assertEqual(asset.device_info.ralph_device_id, device.id)
        self.assertNotEqual(device.service, None)
        self.assertEqual(device.service, asset.service)
        self.assertNotEqual(asset.device_environment, None)
        self.assertEqual(device.device_environment, asset.device_environment)

    def test_sync_field_from_device_to_asset(self):
        """Asset field changed when device was edited."""
        asset = DCAssetFactory(service=None, device_environment=None)
        ci_relation = CIRelationFactory()
        device_environment = ci_relation.child
        service = ci_relation.parent

        device = Device.objects.all()[0]
        device.service = service
        device.device_environment = device_environment
        device.save()

        asset = Asset.objects.all()[0]
        self.assertNotEqual(device.service, None)
        self.assertEqual(device.service, asset.service)
        self.assertNotEqual(asset.device_environment, None)
        self.assertEqual(device.device_environment, asset.device_environment)


class TestAssetAndDeviceLinkage(TestDevicesView, BaseViewsTest):

    asset_factory = DCAssetFactory

    def _get_add_url(self, asset_type):
        url = reverse(
            'add_device',
            kwargs={
                'mode': models_assets.ASSET_TYPE2MODE[asset_type],
            },
        )
        return url

    def _get_edit_url(self, asset_id, asset_type):
        url = reverse(
            'device_edit',
            kwargs={
                'mode': models_assets.ASSET_TYPE2MODE[asset_type],
                'asset_id': asset_id,
            },
        )
        return url

    def _check_fields(self, obj, correct_data):
        for field, correct_value in correct_data.iteritems():
            self.assertEqual(getattr(obj, field), correct_value)

    def _get_asset_with_dummy_device(self, asset_data=None):
        # set device_info=None to prevent creation of device
        if asset_data is None:
            asset_data = {}
        if 'region' not in asset_data:
            asset_data['region'] = Region.get_default_region()
        form_data = self.get_asset_form_data(asset_data)
        return self.add_asset_by_form(form_data)

    def test_asset_spares_existing_device_fields(self):
        """
        - create ralph-core device *core_device*
        - add asset with ralph_device_id = core_device.id
        - check each field (name, remark, dc) is unchanged
        """
        old_value = {
            'dc': 'device dc',
            'name': 'device name',
            'remarks': 'device remarks',
        }
        device = DeviceFactory(**old_value)
        self._check_fields(device, old_value)
        form_data = self.get_asset_form_data({
            'region': Region.get_default_region(),
        })
        form_data['ralph_device_id'] = device.id
        self.add_asset_by_form(form_data)
        device = Device.objects.get(pk=device.id)
        self._check_fields(device, old_value)

    def test_asset_clones_fields_to_new_device(self):
        """Checks if required fields are cloned to dummy device."""
        asset = self._get_asset_with_dummy_device()
        correct_value = {
            'dc': asset.warehouse.name,
            'device_environment': asset.device_environment,
            'name': asset.model.name,
            'remarks': asset.order_no,
            'service': asset.service,
        }
        device = Device.objects.get(sn=asset.sn)
        self._check_fields(device, correct_value)

    def test_device_syncs_with_asset(self):
        """Editing fields on device causes sync to asset."""
        asset = self._get_asset_with_dummy_device()
        device = Device.objects.get(sn=asset.sn)
        device.device_environment = CIRelationFactory().child
        device.save()
        asset = Asset.objects.get(pk=asset.pk)
        self.assertEqual(device.device_environment, asset.device_environment)

    def test_adding_assets_creates_dummy_device(self):
        """
        - add asset without ralph_device_id
        - check each field (dc, device_environment, name, remarks, service)
        is copied to dummy device from asset
        """
        asset = self._get_asset_with_dummy_device()
        correct_value = {
            'dc': asset.warehouse.name,
            'name': asset.model.name,
            'remarks': asset.order_no,
        }
        device = Device.objects.get(sn=asset.sn)
        self.assertEqual(asset.device_info.ralph_device_id, device.id)
        self._check_fields(device, correct_value)

    def test_editing_assets_creates_dummy_device(self):
        """
        edit asset when:
            no devcie -> edit asset + dummy device

        steps:
        - add asset without device
        - edit asset
        - check edited asset is linked to dummy device
        - dummy device has values copied from edited asset
        """
        asset = DCAssetFactory(device_info=None)
        form_data = self.get_asset_form_data()
        Device.objects.get(pk=form_data['ralph_device_id']).delete()
        form_data.update({
            'asset': '',
            'create_stock': 'true',
            'ralph_device_id': '',
            'region': Region.get_default_region().id,
        })
        edit_url = self._get_edit_url(asset.id, form_data['type'])
        self.client.post(edit_url, form_data, follow=True)
        device = Device.objects.get(sn=asset.sn)
        asset = Asset.objects.get(pk=asset.id)
        self.assertEqual(asset.device_info.ralph_device_id, device.id)
        correct_value = {
            'dc': asset.warehouse.name,
            'name': asset.model.name,
            'remarks': asset.order_no,
        }
        self._check_fields(device, correct_value)

    def test_adding_asset_links_device_by_barcode(self):
        """
        - create device with barcode
        - create asset with barcode == device.barcode by form
        - check asset.device_info.ralph_device_id = device.id
        """
        device = DeviceFactory()
        asset = self._get_asset_with_dummy_device({'barcode': device.barcode})
        device = Device.objects.get(barcode=device.barcode)
        self.assertEqual(asset.device_info.ralph_device_id, device.id)

    @unittest.skip("until editing form has option 'link-by-barcode'")
    def test_editing_asset_links_device_by_barcode(self):
        """
        edit asset when:
            - no devcie linked
            - set barcode from an unlinked device -> edit asset + link to
            device

        steps:
        - add asset without device
        - edit asset by form
        - check edited asset is linked to device
        - device has the same values as before linking
        """
        device = DeviceFactory()
        asset = DCAssetFactory(device_info=None)
        form_data = self.get_asset_form_data({'device_info': None})
        form_data.update({
            'ralph_device_id': '',
            'asset': '',
            'barcode': device.barcode,
        })
        edit_url = self._get_edit_url(asset.id, form_data['type'])
        values_before_linking = {
            'dc': device.dc,
            'name': device.name,
            'remarks': device.remarks,
        }
        self.client.post(edit_url, form_data, follow=True)
        device = Device.objects.get(pk=device.id)
        asset = Asset.objects.get(pk=asset.id)
        self.assertEqual(asset.device_info.ralph_device_id, device.id)
        self._check_fields(device, values_before_linking)

    def test_adding_asset_doesnt_link_device_if_already_linked(self):
        '''
        - add asset linked to device (both have same barcode)
        - changed asset barcode (link still exists)
        - add new asset with barcode == device.barcode by form
        - check validation error
        '''
        asset_with_device = DCAssetFactory()
        asset_with_device.barcode = 'changed-barcode'
        asset_with_device.save()

        device_info = DeviceInfoFactory(ralph_device_id=0)
        form_data = self.get_asset_form_data({'device_info': device_info})
        form_data.update({
            'barcode': asset_with_device.get_ralph_device().barcode,
            'region': Region.get_default_region().id,
        })
        add_asset_url = self._get_add_url(form_data['type'])
        response = self.client.post(add_asset_url, form_data, follow=True)
        msg = unicode(response.context['messages']._loaded_messages[0])
        self.assertEqual(
            msg,
            "Device with barcode already exist, check 'force unlink' "
            "option to relink it.",
        )

    @unittest.skip("until editing form has option 'link-by-barcode'")
    def test_editing_asset_doesnt_link_device_if_already_linked(self):
        """
        edit asset when:
            - no devcie linked
            - set barcode from already linked device -> error

        steps:
        - add asset with device
        - edit asset by form, set barcode from linked device
        - check error is shown
        """
        first_asset = DCAssetFactory()
        first_asset.barcode = 'changed-barcode'
        first_asset.save()

        second_asset = DCAssetFactory(device_info=None)
        self.assertTrue(first_asset.linked_device)
        form_data = self.get_asset_form_data({'device_info': None})
        form_data.update({
            'ralph_device_id': '',
            'asset': '',
            'barcode': first_asset.linked_device.barcode,
        })
        edit_url = self._get_edit_url(second_asset.id, form_data['type'])
        response = self.client.post(edit_url, form_data, follow=True)
        msg = unicode(response.context['messages']._loaded_messages[0])
        self.assertEqual(
            msg,
            "Device with barcode already exist, check 'force unlink' "
            "option to relink it.",
        )

    def test_adding_asset_force_relink_device(self):
        '''
        Test old asset is replaced by new asset (in link with device).

        - add asset linked to device (both have same barcode)
        - changed asset barcode (link still exists)
        - add new asset with barcode device.barcode and *force-unlike* checked
        - check old-asset has blank ralph_device_id
        - check new-asset.office_inforalph_device_id == device-id
        '''
        first_asset = DCAssetFactory()
        first_asset.barcode = 'changed-barcode'
        first_asset.save()

        form_data = self.get_asset_form_data({
            'region': Region.get_default_region(),
        })
        form_data.update({
            'ralph_device_id': '',
            'barcode': first_asset.get_ralph_device().barcode,
            'force_unlink': 'true',
        })
        add_asset_url = self._get_add_url(form_data['type'])
        response = self.client.post(add_asset_url, form_data, follow=True)
        asset_id = resolve(response.request['PATH_INFO']).kwargs['asset_id']
        second_asset = models_assets.Asset.objects.get(pk=asset_id)

        linked_device = Device.objects.get(pk=first_asset.id)
        first_asset = Asset.objects.get(pk=first_asset.id)
        self.assertEqual(
            first_asset.device_info.ralph_device_id, None,
        )
        self.assertEqual(
            second_asset.device_info.ralph_device_id, linked_device.id,
        )
        self.assertEqual(second_asset.barcode, linked_device.barcode)

    @unittest.skip("until editing form has option 'link-by-barcode'")
    def test_editing_asset_force_relink_device(self):
        """
        edit asset when:
            - no devcie linked
            - set barcode from already linked device
            - checked 'force_unlink' option -> edit asset + relink device

        steps:
        - add asset a1 with device d1
        - edit asset a2 by form,
            - set barcode from linked device
            - set force_unlink option
        - check a1 is not linked
        - check a2 is linked to device d1
        """
        first_asset = DCAssetFactory()
        first_asset.barcode = 'changed-barcode'
        first_asset.save()

        self.assertTrue(first_asset.linked_device)
        linked_device = first_asset.linked_device
        second_asset = DCAssetFactory(device_info=None)
        form_data = self.get_asset_form_data({'device_info': None})
        form_data.update({
            'ralph_device_id': '',
            'asset': '',
            'barcode': first_asset.linked_device.barcode,
            'force_unlink': 'true',
        })
        edit_url = self._get_edit_url(second_asset.id, form_data['type'])
        self.client.post(edit_url, form_data, follow=True)

        first_asset = Asset.objects.get(pk=first_asset.id)
        second_asset = Asset.objects.get(pk=second_asset.id)
        self.assertFalse(first_asset.linked_device)
        self.assertEqual(
            second_asset.device_info.ralph_device_id, linked_device.id,
        )
        self.assertEqual(second_asset.barcode, linked_device.barcode)


class TestLicenceConnection(BaseViewsTest):

    def formset_dict(self, rows, initial_forms=0,
                     total_forms=0):
        data = {
            'form-TOTAL_FORMS': total_forms or len(rows),
            'form-INITIAL_FORMS': initial_forms,
            'form-MAX_NUM_FORMS': 1000,
        }
        for i, row in enumerate(rows):
            for key, value in row.iteritems():
                data['form-{}-{}'.format(i, key)] = value
        return data

    def test_assigned_to_assets_simple_add(self):
        """
        assigne asset with licence with custom quantity
        """
        licence = LicenceFactory()
        asset = AssetFactory()
        self.assertEqual(LicenceAsset.objects.count(), 0)

        rows = [
            {
                'licence': licence.id,
                'id': '',
                'asset': asset.id,
                'quantity': 200,
            },
        ]
        url = reverse('licence_connections_assets', args=(licence.id,))
        form_data = self.formset_dict(rows)
        response = self.client.post(url, form_data)
        self.assertEqual(LicenceAsset.objects.count(), 1)
        self.assertEqual(LicenceAsset.objects.all()[0].quantity, 200)
        self.assertEqual(len(response.context_data['formset'].errors), 0)

    def test_assigned_to_assets_update(self):
        """
        update licences quantity
        """
        licence_asset = LicenceAssetFactory()
        self.assertEqual(LicenceAsset.objects.count(), 1)

        rows = [
            {
                'licence': licence_asset.licence.id,
                'id': licence_asset.id,
                'asset': licence_asset.asset.id,
                'quantity': 200,
            },
        ]
        url = reverse(
            'licence_connections_assets',
            args=(licence_asset.licence.id,),
        )
        form_data = self.formset_dict(rows, initial_forms=1)
        response = self.client.post(url, form_data)
        self.assertEqual(len(response.context_data['formset'].errors), 0)
        self.assertEqual(LicenceAsset.objects.count(), 1)
        self.assertEqual(LicenceAsset.objects.all()[0].quantity, 200)

    def test_assigned_to_assets_delete(self):
        """
        delete assigned licences to asset
        """
        licence_asset = LicenceAssetFactory()
        self.assertEqual(LicenceAsset.objects.count(), 1)

        rows = []
        url = reverse(
            'licence_connections_assets',
            args=(licence_asset.licence.id,),
        )
        form_data = self.formset_dict(rows, initial_forms=1)
        response = self.client.post(url, form_data)
        self.assertEqual(len(response.context_data['formset'].errors), 0)
        self.assertEqual(LicenceAsset.objects.count(), 0)

    def test_assigned_to_users_simple_add(self):
        """
        assigne user with licence with custom quantity
        """
        licence = LicenceFactory()
        user = UserFactory()
        self.assertEqual(LicenceUser.objects.count(), 0)

        rows = [
            {
                'licence': licence.id,
                'id': '',
                'user': user.id,
                'quantity': 200,
            },
        ]
        url = reverse('licence_connections_users', args=(licence.id,))
        form_data = self.formset_dict(rows)
        response = self.client.post(url, form_data)
        self.assertEqual(LicenceUser.objects.count(), 1)
        self.assertEqual(LicenceUser.objects.all()[0].quantity, 200)
        self.assertEqual(len(response.context_data['formset'].errors), 0)

    def test_assigned_to_users_update(self):
        """
        update licences quantity
        """
        licence_user = LicenceUserFactory()
        self.assertEqual(LicenceUser.objects.count(), 1)

        rows = [
            {
                'licence': licence_user.licence.id,
                'id': licence_user.id,
                'user': licence_user.user.id,
                'quantity': 200,
            },
        ]
        url = reverse(
            'licence_connections_users',
            args=(licence_user.licence.id,),
        )
        form_data = self.formset_dict(rows, initial_forms=1)
        response = self.client.post(url, form_data)
        self.assertEqual(len(response.context_data['formset'].errors), 0)
        self.assertEqual(LicenceUser.objects.count(), 1)
        self.assertEqual(LicenceUser.objects.all()[0].quantity, 200)

    def test_assigned_to_users_delete(self):
        """
        delete assigned licences to user
        """
        licence_user = LicenceUserFactory()
        self.assertEqual(LicenceUser.objects.count(), 1)

        rows = []
        url = reverse(
            'licence_connections_users',
            args=(licence_user.licence.id,),
        )
        form_data = self.formset_dict(rows, initial_forms=1)
        response = self.client.post(url, form_data)
        self.assertEqual(len(response.context_data['formset'].errors), 0)
        self.assertEqual(LicenceUser.objects.count(), 0)


class TestManagementIp(TestDevicesView):
    """Tests for management_ip editing."""

    def test_edit_management_ip(self):
        """Management_ip is editable via asset form."""
        asset = DCAssetFactory()
        url = reverse(
            'device_edit', kwargs={'mode': 'dc', 'asset_id': asset.id}
        )
        data = self.get_object_form_data(
            url, ['asset_form', 'additional_info']
        )
        data['management_ip_0'] = 'hostname.dc1'
        data['management_ip_1'] = '1.1.1.1'
        data['asset'] = ''
        self.client.post(url, data)
        asset = Asset.objects.get(pk=asset.pk)
        self.assertEqual(
            asset.get_ralph_device().management_ip.address,
            '1.1.1.1',
        )

    def test_edit_management_for_dc(self):
        """For DC assets we can edit management_ip."""
        asset = DCAssetFactory()
        url = reverse(
            'device_edit', kwargs={'mode': 'dc', 'asset_id': asset.id}
        )
        response = self.client.get(url)
        self.assertContains(response, 'management_ip')

    def test_no_edit_management_ip_for_bo(self):
        """For DC assets we can't edit management_ip."""
        asset = BOAssetFactory()
        url = reverse('device_edit', kwargs={
            'mode': 'back_office',
            'asset_id': asset.id,
        })
        response = self.client.get(url)
        self.assertNotContains(response, 'management_ip')


class TestAddDeviceInfoForm(TestDevicesView, BaseViewsTest):

    mode = 'dc'
    asset_factory = DCAssetFactory

    def setUp(self):
        super(TestAddDeviceInfoForm, self).setUp()
        self.url = self.get_add_asset_url()

    def test_slotno_required_positive(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=True)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '3',
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertFalse(response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        self.assertTrue(Asset.objects.get(sn=form_data['sn']))

    def test_slotno_required_negative(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=True)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '',
        })
        response = self.client.post(self.url, form_data)
        self.assertIn('slot_no', response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)

    def test_slotno_optional(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=False)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '',
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertFalse(response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        self.assertTrue(Asset.objects.get(sn=form_data['sn']))

    def test_slotno_cant_be_set(self):
        """test slot_no cant be set if asset category is not blade"""
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=False)
        form_data.update({
            'model': blade_model.id,
            'slot_no': 3,
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertIn('slot_no', response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)


class TestEditDeviceInfoForm(TestDevicesView, BaseViewsTest):

    mode = 'dc'
    asset_factory = DCAssetFactory

    def setUp(self):
        super(TestEditDeviceInfoForm, self).setUp()
        self.asset = self.asset_factory()
        self.url = self.edit_obj_url(self.asset.id)

    def test_slotno_required_positive(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=True)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '3',
            'asset': '',
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertFalse(response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        asset = Asset.objects.get(pk=self.asset.id)
        self.assertNotEqual(
            asset.device_info.slot_no, self.asset.device_info.slot_no,
        )
        self.assertEqual(asset.device_info.slot_no, form_data['slot_no'])

    def test_slotno_required_negative(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=True)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '',
            'asset': '',
        })
        response = self.client.post(self.url, form_data)
        self.assertIn('slot_no', response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        asset = Asset.objects.get(pk=self.asset.id)
        self.assertEqual(
            asset.device_info.slot_no, self.asset.device_info.slot_no,
        )
        self.assertNotEqual(asset.device_info.slot_no, form_data['slot_no'])

    def test_slotno_optional(self):
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=False)
        form_data.update({
            'model': blade_model.id,
            'slot_no': '',
            'asset': '',
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertFalse(response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        asset = Asset.objects.get(pk=self.asset.id)
        self.assertEqual(asset.device_info.slot_no, '')
        # check editing was successful, so any field has changed
        self.assertEqual(asset.price, form_data['price'])
        self.assertNotEqual(self.asset.price, asset.price)

    def test_slotno_cant_be_set(self):
        """test slot_no cant be set if asset category is not blade"""
        form_data = self.get_asset_form_data()
        blade_model = AssetModelFactory(category__is_blade=False)
        form_data.update({
            'model': blade_model.id,
            'slot_no': 3,
            'asset': '',
        })
        response = self.client.post(self.url, form_data, follow=True)
        self.assertIn('slot_no', response.context['additional_info'].errors)
        self.assertFalse(response.context['asset_form'].errors)
        asset = Asset.objects.get(pk=self.asset.id)
        self.assertEqual(
            asset.device_info.slot_no, self.asset.device_info.slot_no,
        )
        # check editing was failed, so any field hasn't changed
        self.assertNotEqual(asset.price, form_data['price'])
        self.assertEqual(self.asset.price, asset.price)


class TestLocation(TestDevicesView, BaseViewsTest):

    def _get_form_url(self, assets):
        url_query = '&'.join([
            'select={}'.format(blade.id) for blade in assets
        ])
        form_url = '{}?{}'.format(
            reverse('edit_location_data', args=('dc',)), url_query,
        )
        return form_url

    def _get_form_data(self, common_field_asset, slots_assets):
        form_data = {
            'asset': '',
            'form-INITIAL_FORMS': '2',
            'form-MAX_NUM_FORMS': '1000',
            'form-TOTAL_FORMS': '2',
            # data to check
            'data_center': common_field_asset.device_info.data_center.id,
            'server_room': common_field_asset.device_info.server_room.id,
            'rack': common_field_asset.device_info.rack.id,
            'position': common_field_asset.device_info.position,
            'form-0-id': slots_assets[0].id,
            'form-1-id': slots_assets[1].id,
        }
        return form_data

    def test_selected_blades_allow_editing(self):
        blade = DCAssetFactory(model__category__is_blade=True)
        form_url = self._get_form_url([blade])
        response = self.client.get(form_url, follow=True)
        self.assertIn('chassis_form', response.context)
        self.assertIn('blade_server_formset', response.context)

    def test_non_bladed_selected_show_error(self):
        non_blade = DCAssetFactory(model__category__is_blade=False)
        form_url = self._get_form_url([non_blade])
        response = self.client.get(form_url, follow=True)
        error_msg = unicode(response.context['messages']._loaded_messages[0])
        self.assertIn(non_blade.sn, error_msg)

    def test_edited_successfully(self):
        """
        Checks if 2 assets' data is updated correctly.

        1. create 2 assets
        2. set form data for editing those assets
        3. check if data of the 2 assets is updated correctly
        """
        new_data = DCAssetFactory(device_info__slot_no='1')
        old_slot_numbers = "2 3".split()
        new_slot_numbers = "4 5".split()

        blades_to_edit = [
            DCAssetFactory(
                model__category__is_blade=True,
                device_info__slot_no=old_slot_numbers[idx],
            ) for idx in range(2)
        ]
        form_url = self._get_form_url(blades_to_edit)
        form_data = self._get_form_data(new_data, blades_to_edit)
        form_data.update({
            'form-0-slot_no': new_slot_numbers[0],
            'form-1-slot_no': new_slot_numbers[1],
        })
        self.client.post(form_url, form_data, follow=True)

        # check both assets if are correct
        updated_blades_to_edit = [
            Asset.objects.get(pk=blade.id) for blade in blades_to_edit
        ]
        for idx, blade in enumerate(updated_blades_to_edit):
            for field_name in [
                'data_center', 'server_room', 'rack', 'position',
            ]:
                self.assertEqual(
                    getattr(blade.device_info, field_name),
                    getattr(new_data.device_info, field_name),
                )
            self.assertEqual(blade.device_info.slot_no, new_slot_numbers[idx])

    def test_check_same_slot_number_fails_validation(self):
        """
        Check updating 2 assets with same slot-number fails validation.

        1. create 2 assets
        2. set form data for editing those assets (slot-number is the same)
        3. check if validation errors shows
        """
        new_data = DCAssetFactory(device_info__slot_no='1')
        old_slot_numbers = "2 3".split()
        new_slot_numbers = "4"

        blades_to_edit = [
            DCAssetFactory(
                model__category__is_blade=True,
                device_info__slot_no=old_slot_numbers[idx],
            ) for idx in range(2)
        ]
        form_url = self._get_form_url(blades_to_edit)
        form_data = self._get_form_data(new_data, blades_to_edit)
        form_data.update({
            'form-0-slot_no': new_slot_numbers,
            'form-1-slot_no': new_slot_numbers,
        })
        response = self.client.post(form_url, form_data, follow=True)

        for form in response.context['blade_server_formset'].forms:
            self.assertEqual(
                form.errors['slot_no'],
                ChassisBulkEdit.SAME_SLOT_MSG_ERROR,
            )
