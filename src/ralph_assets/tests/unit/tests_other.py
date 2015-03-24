# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import datetime

from dj.choices import Country
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from ralph.account.models import Region
from ralph.discovery.tests.util import DeviceFactory

from ralph_assets import models_assets
from ralph_assets.others import get_assets_rows, get_licences_rows
from ralph_assets.tests.utils import UserFactory
from ralph_assets.tests.utils.assets import (
    AssetFactory,
    AssetCategoryFactory,
    AssetManufacturerFactory,
    AssetModelFactory,
    BOAssetFactory,
    DataCenterFactory,
    DCAssetFactory,
    DeviceInfoFactory,
    RackFactory,
    ServerRoomFactory,
    WarehouseFactory,
)
from ralph_assets.tests.utils.licences import (
    LicenceFactory,
    SoftwareCategoryFactory,
)
from ralph_assets.utils import iso2_to_iso3, iso3_to_iso2


class TestExportRelations(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user = UserFactory(
            username='user',
            is_staff=False,
            is_superuser=False,
            first_name='Elmer',
            last_name='Stevens',
        )
        cls.owner = UserFactory(
            username='owner',
            is_staff=False,
            is_superuser=False,
            first_name='Eric',
            last_name='Brown',
        )

        cls.category = AssetCategoryFactory(name='Subcategory')
        cls.model = AssetModelFactory(
            name='Model1',
            category=cls.category,
            manufacturer=AssetManufacturerFactory(name='Manufacturer1')
        )
        cls.warehouse = WarehouseFactory(name='Warehouse')
        cls.asset = AssetFactory(
            order_no='Order No2',
            invoice_no='invoice-6666',
            invoice_date=datetime.date(2014, 4, 28),
            support_type='Support d2d',
            sn='1111-1111-1111-1111',
            model=cls.model,
            user=cls.user,
            owner=cls.owner,
            barcode='br-666',
            niw='niw=666',
            warehouse=cls.warehouse,
        )
        cls.software_category = SoftwareCategoryFactory(name='soft-cat1')
        cls.licence1 = LicenceFactory(
            invoice_date=datetime.date(2014, 4, 28),
            invoice_no="666-999-666",
            niw="niw-666",
            number_bought=10,
            price=1000.0,
            region=Region.get_default_region(),
            sn="test-sn",
            software_category=cls.software_category,
        )
        cls.licence1.save()

    def test_assets_rows(self):
        rows = [item for item in get_assets_rows()]

        self.assertListEqual(
            rows,
            [
                [
                    'id', 'niw', 'barcode', 'sn', 'model__category__name',
                    'model__manufacturer__name', 'model__name',
                    'user__username', 'user__first_name', 'user__last_name',
                    'owner__username', 'owner__first_name',
                    'owner__last_name', 'status', 'service_name__name',
                    'property_of', 'warehouse__name', 'invoice_date',
                    'invoice_no', 'region__name',
                ],
                [
                    self.asset.id, 'niw=666', 'br-666',
                    '1111-1111-1111-1111', 'Subcategory', 'Manufacturer1',
                    'Model1', 'user', 'Elmer', 'Stevens', 'owner', 'Eric',
                    'Brown', 1, None, None, 'Warehouse',
                    datetime.date(2014, 4, 28), 'invoice-6666',
                    'Default region',
                ],
            ]
        )

    def test_licences_rows(self):
        self.licence1.assign(self.asset)
        self.licence1.assign(self.user)
        self.licence1.assign(self.owner)
        rows = [item for item in get_licences_rows()]
        self.assertListEqual(
            rows,
            [
                [
                    'niw', 'software_category', 'number_bought', 'price',
                    'invoice_date', 'invoice_no', 'id', 'barcode', 'niw',
                    'user__username', 'user__first_name', 'user__last_name',
                    'owner__username', 'owner__first_name',
                    'owner__last_name', 'region__name', 'username',
                    'first_name', 'last_name', 'single_cost',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', '', '', '', '', '', '', '', '', '', '', '',
                    '', '',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', str(self.asset.id), 'br-666', 'niw=666',
                    'user', 'Elmer', 'Stevens', 'owner', 'Eric', 'Brown',
                    'Default region', '', '', '', '', '', '', '', '', '', '',
                    '', '', '',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', '', '', '', '', '', '', '', '', '', '',
                    'user', 'Elmer', 'Stevens', '100.00',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', '', '', '', '', '', '', '', '', '', '',
                    'owner', 'Eric', 'Brown', '100.00',
                ],
            ]
        )

    def test_licences_rows_only_assigned(self):
        self.licence1.assign(self.asset)
        self.licence1.assign(self.user)
        self.licence1.assign(self.owner)
        rows = [item for item in get_licences_rows(only_assigned=True)]

        self.assertListEqual(
            rows,
            [
                [
                    'niw', 'software_category', 'number_bought', 'price',
                    'invoice_date', 'invoice_no', 'id', 'barcode', 'niw',
                    'user__username', 'user__first_name', 'user__last_name',
                    'owner__username', 'owner__first_name',
                    'owner__last_name', 'region__name', 'username',
                    'first_name', 'last_name', 'single_cost',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', str(self.asset.id), 'br-666', 'niw=666',
                    'user', 'Elmer', 'Stevens', 'owner', 'Eric', 'Brown',
                    'Default region', '', '', '', '', '', '', '', '', '', '',
                    '', '', '',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', '', '', '', '', '', '', '', '', '', '',
                    'user', 'Elmer', 'Stevens', '100.00',
                ],
                [
                    'niw-666', 'soft-cat1', '10', '1000.00', '2014-04-28',
                    '666-999-666', '', '', '', '', '', '', '', '', '', '',
                    'owner', 'Eric', 'Brown', '100.00',
                ],
            ]
        )


class TestHostnameGenerator(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.user = UserFactory()
        cls.user_pl = UserFactory()
        cls.user_pl.profile.country = Country.pl
        cls.user_pl.profile.save()
        cls.cat = AssetCategoryFactory()
        cls.cat1 = AssetCategoryFactory()
        cls.cat2 = AssetCategoryFactory()
        cls.cat3 = AssetCategoryFactory()
        cls.asset1 = BOAssetFactory()
        cls.asset2 = BOAssetFactory()

    @classmethod
    def tearDownClass(cls):
        call_command('flush', interactive=False, verbosity=0)

    def _check_hostname_not_generated(self, asset):
        asset._try_assign_hostname(True)
        changed_asset = models_assets.Asset.objects.get(pk=asset.id)
        self.assertEqual(changed_asset.hostname, None)

    def _check_hostname_is_generated(self, asset):
        asset._try_assign_hostname(True)
        changed_asset = models_assets.Asset.objects.get(pk=asset.id)
        self.assertTrue(len(changed_asset.hostname) > 0)

    def test_generate_first_hostname(self):
        """Scenario:
         - none of assets has hostname
         - after generate first of asset have XXXYY00001 in hostname field
        """
        category = AssetCategoryFactory(code='PC')
        model = AssetModelFactory(category=category)
        asset = BOAssetFactory(model=model, owner=self.user_pl, hostname='')
        template_vars = {
            'code': asset.model.category.code,
            'country_code': asset.country_code,
        }
        asset.generate_hostname(template_vars=template_vars)
        self.assertEqual(asset.hostname, 'POLPC00001')

    def test_generate_next_hostname(self):
        category = AssetCategoryFactory(code='PC')
        model = AssetModelFactory(category=category)
        asset = BOAssetFactory(model=model, owner=self.user_pl, hostname='')
        BOAssetFactory(owner=self.user_pl, hostname='POLSW00003')
        models_assets.AssetLastHostname.increment_hostname(prefix='POLPC')
        models_assets.AssetLastHostname.increment_hostname(prefix='POLPC')
        template_vars = {
            'code': asset.model.category.code,
            'country_code': asset.country_code,
        }
        asset.generate_hostname(template_vars=template_vars)
        self.assertEqual(asset.hostname, 'POLPC00003')

    def test_cant_generate_hostname_for_model_without_category(self):
        model = AssetModelFactory(category=None)
        asset = BOAssetFactory(model=model, owner=self.user_pl, hostname='')
        self._check_hostname_not_generated(asset)

    def test_can_generate_hostname_for_model_with_hostname(self):
        category = AssetCategoryFactory(code='PC')
        model = AssetModelFactory(category=category)
        asset = BOAssetFactory(model=model, owner=self.user_pl)
        self._check_hostname_is_generated(asset)

    def test_cant_generate_hostname_for_model_without_user(self):
        model = AssetModelFactory()
        asset = BOAssetFactory(model=model, owner=None, hostname='')
        self._check_hostname_not_generated(asset)

    def test_cant_generate_hostname_for_model_without_user_and_category(self):
        model = AssetModelFactory(category=None)
        asset = BOAssetFactory(model=model, owner=None, hostname='')
        self._check_hostname_not_generated(asset)

    def test_generate_next_hostname_out_of_range(self):
        category = AssetCategoryFactory(code='PC')
        model = AssetModelFactory(category=category)
        asset = BOAssetFactory(model=model, owner=self.user_pl, hostname='')
        models_assets.AssetLastHostname.objects.create(
            prefix='POLPC', counter=99999
        )
        template_vars = {
            'code': asset.model.category.code,
            'country_code': asset.country_code,
        }
        asset.generate_hostname(template_vars=template_vars)
        self.assertEqual(asset.hostname, 'POLPC100000')

    def test_convert_iso2_to_iso3(self):
        self.assertEqual(iso2_to_iso3['PL'], 'POL')

    def test_convert_iso3_to_iso2(self):
        self.assertEqual(iso3_to_iso2['POL'], 'PL')


@override_settings(ASSETS_AUTO_ASSIGN_HOSTNAME=True)
class TestHostnameAssigning(TestCase):
    neutral_status = models_assets.AssetStatus.new
    trigger_status = models_assets.AssetStatus.in_progress

    @classmethod
    def setUpClass(cls):
        cls.owner = UserFactory()
        cls.neutral_status = models_assets.AssetStatus.new
        cls.trigger_status = models_assets.AssetStatus.in_progress
        cls.owner_country_name = models_assets.get_user_iso3_country_name(
            cls.owner
        )

    def test_assigning_when_no_hostname(self):
        """
        Generate hostname when it's none.
        """
        no_hostname_asset = BOAssetFactory(**{'hostname': None})
        self.assertEqual(no_hostname_asset.hostname, None)
        no_hostname_asset._try_assign_hostname(True)
        self.assertNotEqual(no_hostname_asset.hostname, None)

    def test_assigning_when_different_country(self):
        """
        Generate hostname when user has diffrent country than country from
        hostname.
        """
        asset = BOAssetFactory(**{'owner': self.owner})
        old_hostname = asset.hostname
        self.assertNotIn(self.owner_country_name, asset.hostname)
        asset._try_assign_hostname(True)
        self.assertNotEqual(asset.hostname, old_hostname)
        self.assertIn(self.owner_country_name, asset.hostname)

    def test_assigning_when_same_country(self):
        """
        Keep existing hostname when user has the same country name
        """
        def _asset_from_country(iso3_country):
            asset = BOAssetFactory()
            hostname = asset.hostname.replace('XXX', iso3_country)
            asset.hostname = hostname
            asset.save()
            return asset
        asset = _asset_from_country(self.owner_country_name)
        old_hostname = asset.hostname
        asset._try_assign_hostname(True)
        self.assertEqual(asset.hostname, old_hostname)


class TestLinkedDevice(TestCase):
    def test_bo_asset(self):
        asset = BOAssetFactory()
        self.assertEqual(asset.linked_device, None)

    def test_dc_asset_with_linked_device(self):
        core_device = DeviceFactory()
        device_info = DeviceInfoFactory(ralph_device_id=core_device.id)
        asset = DCAssetFactory(device_info=device_info)
        self.assertEqual(asset.linked_device, core_device)

    def test_dc_asset_without_linked_device(self):
        asset = DCAssetFactory(device_info=None)
        asset.save()
        self.assertEqual(asset.linked_device, None)

    def update_device(self, device, field, value):
        setattr(device, field, value)
        device.save()

    def test_finding_device_to_link(self):
        device_to_check = DeviceFactory(barcode=None, sn=None)
        dc_asset = DCAssetFactory(device_info=None)

        self.assertEqual(dc_asset.find_device_to_link(), None)

        self.update_device(device_to_check, 'sn', dc_asset.sn)
        self.assertEqual(dc_asset.find_device_to_link(), device_to_check)

        self.update_device(device_to_check, 'sn', None)
        self.update_device(device_to_check, 'barcode', dc_asset.barcode)
        self.assertEqual(dc_asset.find_device_to_link(), device_to_check)

        self.update_device(device_to_check, 'sn', dc_asset.sn)
        self.update_device(device_to_check, 'barcode', dc_asset.barcode)
        self.assertEqual(dc_asset.find_device_to_link(), device_to_check)


class TestDeviceInfoValidation(TestCase):

    def setUp(self):
        self.form_data = {
            'ralph_device_id': '',
        }
        self.rack = RackFactory()
        self.correct_device_info = DeviceInfoFactory(
            rack=self.rack,
            server_room=self.rack.server_room,
            data_center=self.rack.server_room.data_center,
        )
        self.asset = DCAssetFactory(device_info=self.correct_device_info)

    def test_data_center_and_server_room_relation(self):
        '''test if picked server-room is owned by picked data-center'''
        device_info = self.correct_device_info
        # positive
        device_info.clean_fields()

        # nagative
        device_info = self.correct_device_info
        device_info.data_center = DataCenterFactory()
        self.assertNotEqual(
            device_info.data_center,
            device_info.server_room.data_center,
        )
        with self.assertRaises(ValidationError) as exc:
            device_info.clean_fields()
        self.assertIn('server_room', exc.exception.message_dict)

    def test_server_room_relation(self):
        '''test if picked rack is owned by picked server-room'''
        device_info = self.correct_device_info
        # positive
        device_info.clean_fields()

        # nagative
        device_info = self.correct_device_info
        device_info.server_room = ServerRoomFactory()
        device_info.data_center = device_info.server_room.data_center
        self.assertNotEqual(
            device_info.rack.server_room,
            device_info.server_room,
        )
        with self.assertRaises(ValidationError) as exc:
            device_info.clean_fields()
        self.assertIn('rack', exc.exception.message_dict)

    def test_position_requires_width(self):
        '''test if picked orientation is owned by picked position - width'''
        device_info = self.correct_device_info
        device_info.position = 0
        # positive
        device_info.orientation = models_assets.Orientation.left
        device_info.clean_fields()
        device_info.orientation = models_assets.Orientation.right
        device_info.clean_fields()
        # nagative
        device_info.orientation = models_assets.Orientation.front
        with self.assertRaises(ValidationError) as exc:
            device_info.clean_fields()
        self.assertIn('orientation', exc.exception.message_dict)

    def test_position_requires_height(self):
        '''test if picked orientation is owned by picked position - height'''
        device_info = self.correct_device_info
        positive_non_zero = 5
        device_info.position = positive_non_zero
        # positive
        device_info.orientation = models_assets.Orientation.front
        device_info.clean_fields()
        device_info.orientation = models_assets.Orientation.middle
        device_info.clean_fields()
        device_info.orientation = models_assets.Orientation.back
        device_info.clean_fields()
        # nagative
        device_info.orientation = models_assets.Orientation.left
        with self.assertRaises(ValidationError) as exc:
            device_info.clean_fields()
        self.assertIn('orientation', exc.exception.message_dict)

    def test_position_is_valid(self):
        '''test if picked position works with max_u_height'''
        device_info = self.correct_device_info
        device_info.position = device_info.rack.max_u_height - 1
        # positive
        device_info.clean_fields()
        # nagative
        device_info.position = device_info.rack.max_u_height + 1
        with self.assertRaises(ValidationError) as exc:
            device_info.clean_fields()
        self.assertIn('position', exc.exception.message_dict)


class TestAssetStatuses(TestCase):

    def setUp(self):
        pass

    def test_return_all_choices_if_not_set(self):
        self.assertEqual(
            models_assets.AssetStatus.data_center(required=True),
            models_assets.AssetStatus(),
        )
        self.assertEqual(
            models_assets.AssetStatus.back_office(required=True),
            models_assets.AssetStatus(),
        )

    @override_settings(ASSET_STATUSES={
        'data_center': ['new']
    })
    def test_return_only_choices_from_settings(self):
        correct_choices = [
            (models_assets.AssetStatus.new.id,
             models_assets.AssetStatus.new.name),
        ]
        self.assertEqual(
            models_assets.AssetStatus.data_center(required=True),
            correct_choices,
        )

    @override_settings(ASSET_STATUSES={
        'data_center': ['undefined-status']
    })
    def test_raise_exception_when_unknown_status(self):
        self.assertRaises(
            Exception, models_assets.AssetStatus.data_center, (True,),
        )

    def test_exclude_blank(self):
        self.assertEqual(
            len(models_assets.AssetStatus.data_center(required=True)),
            len(models_assets.AssetStatus()),
        )

    def test_include_blank(self):
        found = models_assets.AssetStatus.data_center(required=False)
        self.assertEqual(len(found), len(models_assets.AssetStatus()) + 1)
        BLANK_IDX = 0
        self.assertNotIn(found[BLANK_IDX], models_assets.AssetStatus())
