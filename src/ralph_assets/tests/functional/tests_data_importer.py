# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.utils import override_settings
from ralph.cmdb.tests.utils import CIRelationFactory
from ralph.discovery.tests.util import DeviceFactory

from ralph_assets.licences.models import (
    AssetType,
    Licence,
)
from ralph_assets.models_assets import Asset
from ralph_assets.tests.utils import (
    ClientMixin,
)
from ralph_assets.tests.utils.assets import (
    BOAssetFactory,
    DCAssetFactory,
)
from ralph_assets.tests.utils.licences import (
    LicenceFactory,
)


class TestImport(ClientMixin, TestCase):
    # TODO: merge it with TestDataImporter?
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
            updated_asset = Asset.objects.get(id=asset.id)
            self.assertEqual(
                getattr(updated_asset, field), new_value
            )


class TestDataImporter(object):
    SEP = ','
    upload_model = None
    upload_asset_type = None
    Model = None
    ModelFactory = None
    base_excluded_fields = set()

    def setUp(self):
        self.login_as_superuser()
        self.url = reverse('xls_upload')
        self.excluded_fields = self.base_excluded_fields.copy()

    def _fields2choices(self, fields):
        return {'column_choice-{}'.format(f): f for f in fields}

    def _format_row(self, row):
        return self.SEP.join(['"{}"'.format(item) for item in row])

    def _get_csv_string(self, cols, vals):
        header = self._format_row(cols)
        rows_string = '\n'.join([self._format_row(row) for row in vals])
        csv_string = '\n'.join([header, rows_string])
        return csv_string

    def _get_csv_data(self, important_data={}, use_existing=True):
        """
        Return dict, where:
            *keys* are names of model fields (model is set by
                self.ModelFactory)
            *values* are just field values of model, unless field is foreign
                key. If so then *name* of related object is taken.
            Example:
                modelFactory = Asset, field = price:
                    {'price', Asset.price}
                modelFactory = Asset, field = warehouse:
                    {'warehouse', Asset.warehouse.name}
        """
        csv_data = {}
        obj = self.ModelFactory()
        for field in obj._meta.fields:
            if field.name in self.excluded_fields:
                continue
            field_value = getattr(obj, field.name)
            if field.rel:
                # foreign key, so get as string
                field_value = field_value.name
                if not use_existing:
                    field_value += '-new'
            csv_data[field.name] = field_value
        obj.delete()
        if not important_data:
            important_data = {}
        csv_data.update(important_data)
        return csv_data

    def _check_form_errors(self, response, step):
        errors = getattr(response.context['wizard']['form'], 'errors', None)
        msg = 'step {step} failed, form errors: {form_errors!r}'.format(
            form_errors=errors, step=step,
        )
        self.assertFalse(errors, msg)

    def _import_by_csv(self, fields, values):
        self.client.get(self.url)
        csv_string = self._get_csv_string(fields, values)

        step1_post = {
            'upload-asset_type': self.upload_asset_type,
            'upload-model': self.upload_model,
            'upload-file': SimpleUploadedFile('test.csv', csv_string),
            'xls_upload_view-current_step': 'upload',
        }
        response = self.client.post(self.url, step1_post)
        self._check_form_errors(response, step=1)
        self.assertContains(response, 'column_choice')
        self.assertContains(response, 'step 2/3')

        step2_post = {
            'xls_upload_view-current_step': 'column_choice',
        }
        step2_post.update(self._fields2choices(fields))
        response = self.client.post(self.url, step2_post)
        self._check_form_errors(response, step=2)
        self.assertContains(response, 'step 3/3')

        step3_post = {
            'xls_upload_view-current_step': 'confirm',
        }
        response = self.client.post(self.url, step3_post)
        self._check_form_errors(response, step=3)
        self.assertContains(response, 'Import done')

    def _check_object_against_csv(self, obj, csv_data):
        for field_name, csv_value in csv_data.iteritems():
            obj_value = getattr(obj, field_name)
            if hasattr(obj_value, 'name'):
                obj_value = getattr(obj, field_name).name
            msg = 'Incorrect field {!r} value {!r} != {!r}'.format(
                field_name, obj_value, csv_value,
            )
            self.assertEqual(obj_value, csv_value, msg)

    def test_add_by_import(self):
        """
        Uses existing foreign fields.
        """
        csv_data = self._get_csv_data()
        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    def test_add_by_import_with_new_foreign_keys(self):
        """
        Creates foreign fields from text values.
        """
        csv_data = self._get_csv_data(use_existing=False)
        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    def test_update_by_import(self):
        """
        Uses existing foreign fields.
        """
        self.excluded_fields.remove('id')
        updated_obj = self.ModelFactory()
        csv_data = self._get_csv_data(important_data={'id': updated_obj.id})

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        updated_obj = self.Model.objects.get(pk=updated_obj.id)
        self._check_object_against_csv(updated_obj, csv_data)

    def test_update_by_import_with_new_foreign_fields(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.remove('id')
        updated_obj = self.ModelFactory()
        csv_data = self._get_csv_data(
            important_data={'id': updated_obj.id}, use_existing=False,
        )

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        updated_obj = self.Model.objects.get(pk=updated_obj.id)
        self._check_object_against_csv(updated_obj, csv_data)


class TestLicenceDataImporter(TestDataImporter, ClientMixin, TestCase):

    upload_model = 'ralph_assets.licence'
    upload_asset_type = AssetType.back_office.id
    Model = Licence
    ModelFactory = LicenceFactory
    base_excluded_fields = set([
        'cache_version', 'created', 'id', 'level', 'lft', 'modified',
        'parent', 'rght', 'saving_user', 'tree_id',
    ])

    def test_add_by_import_with_new_foreign_keys(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.update(['region'])
        csv_data = self._get_csv_data(use_existing=False)

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    def test_update_by_import_with_new_foreign_fields(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.remove('id')
        self.excluded_fields.update(['region'])

        updated_obj = self.ModelFactory()
        csv_data = self._get_csv_data(
            important_data={'id': updated_obj.id}, use_existing=False,
        )

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        updated_obj = self.Model.objects.get(pk=updated_obj.id)
        self._check_object_against_csv(updated_obj, csv_data)


class TestBOAssetDataImporter(TestDataImporter, ClientMixin, TestCase):

    upload_model = 'ralph_assets.asset'
    upload_asset_type = AssetType.back_office.id
    Model = Asset
    ModelFactory = BOAssetFactory
    base_excluded_fields = set([
        'cache_version', 'created', 'device_info', 'id', 'modified', 'note',
        'modified_by', 'part_info', 'saving_user', 'support_price',
        'support_period', 'support_type', 'support_void_reporting',
        # these ones can't be created through import
        'created_by', 'owner', 'user',
        # TODO: add|extend-existing test for office_info crap and remove it
        'office_info',
    ])

    def test_add_by_import_with_new_foreign_keys(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.update(
            ['service', 'device_environment', 'region'],
        )
        csv_data = self._get_csv_data(use_existing=False)

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    def test_update_by_import_with_new_foreign_fields(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.remove('id')
        self.excluded_fields.update(
            ['service', 'device_environment', 'region'],
        )
        updated_obj = self.ModelFactory()
        csv_data = self._get_csv_data(
            important_data={'id': updated_obj.id}, use_existing=False,
        )

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        updated_obj = self.Model.objects.get(pk=updated_obj.id)
        self._check_object_against_csv(updated_obj, csv_data)


class TestDCAssetDataImporter(TestDataImporter, ClientMixin, TestCase):

    upload_model = 'ralph_assets.asset'
    upload_asset_type = AssetType.data_center.id
    Model = Asset
    ModelFactory = DCAssetFactory
    base_excluded_fields = set([
        'cache_version', 'created', 'office_info', 'id', 'modified', 'note',
        'modified_by', 'part_info', 'saving_user', 'support_price',
        'support_period', 'support_type', 'support_void_reporting',
        # these ones can't be created through import
        'created_by', 'owner', 'user',
        # shouldn't be in device model, silence here error from there
        'hostname',
        # TODO: add|extend-existing test for device_info crap and remove it
        'device_info',
    ])

    def test_add_by_import(self):
        """
        Uses existing foreign fields.
        """
        device = DeviceFactory()
        csv_data = self._get_csv_data(
            important_data={'barcode': device.barcode},
        )
        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    @override_settings(DATA_IMPORTER={'import_unmatched_assets': True})
    def test_add_unmatched_when_matching_is_disabled(self):
        csv_data = self._get_csv_data(
            important_data={
                'barcode': 'not-matched-barcode',
                'sn': 'not-matched-sn',
            },
        )
        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.get(sn=csv_data['sn'])
        self.assertTrue(added_obj)
        self._check_object_against_csv(added_obj, csv_data)
        self.assertTrue(added_obj.get_ralph_device())

    @override_settings(DATA_IMPORTER={'import_unmatched_assets': False})
    def test_dont_add_unmatched_when_matching_is_enabled(self):
        csv_data = self._get_csv_data(
            important_data={
                'barcode': 'not-matched-barcode',
                'sn': 'not-matched-sn',
            },
        )
        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        with self.assertRaises(self.Model.DoesNotExist):
            self.Model.objects.get(sn=csv_data['sn'])

    def test_add_by_import_with_new_foreign_keys(self):
        """
        Creates foreign fields from text values.
        """
        device = DeviceFactory()
        service_env = CIRelationFactory()
        self.excluded_fields.update(
            ['service', 'device_environment', 'region'],
        )
        csv_data = self._get_csv_data(
            important_data={
                'barcode': device.barcode,
                'device_environment': service_env.child.name,
                'service': service_env.parent.name,
            }, use_existing=False,
        )

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        added_obj = self.Model.objects.latest('id')
        self._check_object_against_csv(added_obj, csv_data)

    def test_update_by_import_with_new_foreign_fields(self):
        """
        Creates foreign fields from text values.
        """
        self.excluded_fields.remove('id')
        self.excluded_fields.update(
            ['service', 'device_environment', 'region'],
        )
        updated_obj = self.ModelFactory()
        csv_data = self._get_csv_data(
            important_data={'id': updated_obj.id}, use_existing=False,
        )

        self._import_by_csv(csv_data.keys(), [csv_data.values()])
        updated_obj = self.Model.objects.get(pk=updated_obj.id)
        self._check_object_against_csv(updated_obj, csv_data)
