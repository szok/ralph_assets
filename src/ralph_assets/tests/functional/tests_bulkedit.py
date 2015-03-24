# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.utils import override_settings

from ralph.account.models import Region
from ralph_assets import models_assets
from ralph_assets.models_assets import AssetStatus
from ralph_assets.tests.utils import UserFactory
from ralph_assets.tests.utils.assets import (
    AssetFactory,
    BOAssetFactory,
    AssetCategoryFactory,
    AssetModelFactory,
    AssetOwnerFactory,
    ServiceFactory,
    WarehouseFactory,
)
from ralph_assets.tests.utils.licences import LicenceFactory
from ralph_assets.tests.util import get_bulk_edit_post_data

from ralph.ui.tests.global_utils import login_as_su


class TestBulkEdit(TestCase):
    """Test bulkedit for generic actions

    Scenario:
    1. Add two assets
    2. Check if data was saved
    """
    def setUp(self):
        self.client = login_as_su()
        self.category = AssetCategoryFactory()
        self.asset = AssetFactory()
        self.asset1 = AssetFactory()
        self.model = AssetModelFactory(category=self.category)
        self.model1 = AssetModelFactory(category=self.category)
        self.user = UserFactory()
        self.warehouse = WarehouseFactory()
        self.assetOwner = AssetOwnerFactory()
        self.asset_service = ServiceFactory()
        self.common_asset_data = {  # DC & BO common data
            'barcode': 'barcode',
            'deprecation_rate': 25.77,
            'invoice_date': '2011-11-14',
            'invoice_no': 'invoice_no',
            'model': self.model,
            'order_no': 'order_no',
            'owner': self.user,
            'price': 101.22,
            'property_of': self.assetOwner,
            'service_name': self.asset_service,
            'source': models_assets.AssetSource.shipment,
            'status': models_assets.AssetStatus.in_progress,
            'task_url': 'www.test.com',
            'user': self.user,
            'warehouse': self.warehouse,
        }

    def test_edit_via_bulkedit_form(self):
        url = '/assets/dc/bulkedit/?select=%s&select=%s' % (
            self.asset.id, self.asset1.id)
        content = self.client.get(url)
        self.assertEqual(content.status_code, 200)

        post_data = get_bulk_edit_post_data({
            'id': self.asset.id,
            'model': self.model.id,
            'invoice_no': 'Invoice No1',
            'order_no': 'Order No1',
            'invoice_date': '2012-02-02',
            'status': AssetStatus.in_progress.id,
            'sn': '3333-3333-3333-3333',
            'barcode': 'bc-3333-3333-3333-3333',
        }, {
            'id': self.asset1.id,
            'model': self.model1.id,
            'invoice_no': 'Invoice No2',
            'order_no': 'Order No2',
            'invoice_date': '2011-02-03',
            'status': AssetStatus.waiting_for_release.id,
            'sn': '4444-4444-4444-4444',
            'barcode': 'bc-4444-4444-4444-4444',
        })

        response = self.client.post(url, post_data, follow=True)

        # Find success message
        self.assertTrue('Changes saved.' in response.content)

        # if everything is ok, server return response code = 302, and
        # redirect us to /assets/dc/search given response code 200
        self.assertRedirects(
            response,
            url,
            status_code=302,
            target_status_code=200,
        )

        # Simulate reopening bulkedit form to check if data were written
        new_view = self.client.get(url)
        fields = new_view.context['formset'].queryset

        correct_data = [
            dict(
                model=unicode(self.model),
                invoice_no='Invoice No1',
                order_no='Order No1',
                invoice_date='2012-02-02',
                status=AssetStatus.in_progress.id,
                sn='3333-3333-3333-3333',
                barcode='bc-3333-3333-3333-3333',
            ),
            dict(
                model=unicode(self.model1),
                invoice_no='Invoice No2',
                order_no='Order No2',
                invoice_date='2011-02-03',
                status=AssetStatus.waiting_for_release.id,
                sn='4444-4444-4444-4444',
                barcode='bc-4444-4444-4444-4444',
            )
        ]
        for counter, data in enumerate(correct_data):
            for key in data.keys():
                self.assertEqual(
                    unicode(getattr(fields[counter], key)), unicode(data[key]),
                    'returned {} expected {} for field {}'.format(
                        getattr(fields[counter], key), data[key], key
                    )
                )

    def _test_showing_form_data(self, mode, asset_id, asset_data):
        """
        Common code for tests:
        - test_showing_dc_form_data
        - test_showing_bo_form_data
        """
        url = ''.join([
            reverse('bulkedit', kwargs={'mode': mode}),
            '?select={}'.format(asset_id),
        ])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        for field_name, value in asset_data.items():
            form_val = unicode(
                response.context['formset'].forms[0][field_name].value(),
            )
            try:
                expected = value.id
            except AttributeError:
                expected = value
            msg = 'Bulkedit field "{}" got "{}" instead of "{}" in {} mode.'
            self.assertEqual(form_val, unicode(expected), msg.format(
                field_name, form_val, expected, mode,
            ))

    def test_showing_dc_form_data(self):
        """
        1. add DC asset,
        2. open asset in bulk mode,
        3. check if all fields are set like the added asset.
        """
        dc_asset_data = self.common_asset_data.copy()
        dc_asset_data.update({'sn': 'dc-sn-number'})
        dc_asset = AssetFactory(**dc_asset_data)
        self._test_showing_form_data(
            'dc', dc_asset.id, dc_asset_data
        )

    def test_showing_bo_form_data(self):
        """
        1. add BO asset,
        2. open asset in bulk mode,
        3. check if all fields are set like the added asset.
        """
        bo_asset_data = self.common_asset_data.copy()
        bo_asset_data.update({
            'hostname': 'POLPC12345',
        })
        bo_asset_data.update({
            'sn': 'bo-sn-number',
            'type': models_assets.AssetType.back_office,
            'provider': 'provider',
            'region': Region.get_default_region(),
        })

        bo_asset = BOAssetFactory(**bo_asset_data)

        self._test_showing_form_data(
            'back_office', bo_asset.id, bo_asset_data
        )

    @override_settings(MAX_BULK_EDIT_SIZE=5)
    def test_bulk_edit_max_items_at_once(self):
        """Scenario:
         - user selected more than MAX_BULK_EDIT_SIZE
         - user should see message error
        """
        number_of_selected_items = settings.MAX_BULK_EDIT_SIZE + 1
        licences = [LicenceFactory() for _ in range(number_of_selected_items)]
        url = reverse('licence_bulkedit')
        url += '?' + '&'.join(['select={}'.format(obj.pk) for obj in licences])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)


class TestBulkEditAsset(TestCase):

    def setUp(self):
        self.client = login_as_su()

    def test_edit_form(self):
        url = reverse('bulkedit', args=('dc',))
        self.client.get(url)
