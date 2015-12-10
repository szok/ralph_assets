# -*- coding: utf-8 -*-
"""Templatetags specific for ralph_assets"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from django import template
from django.conf import settings
from django.core.urlresolvers import reverse
from django.forms import CheckboxInput

from ralph_assets.models import get_edit_url, Transition
from ralph_assets.models_support import Support
from ralph_assets.models_assets import ASSET_TYPE2MODE


register = template.Library()


@register.simple_tag
def edit_url(object_):
    """Returns the url of edit page for a given object (currently implemented
    for Users, expand if needed)
    """
    return get_edit_url(object_)


@register.inclusion_tag('assets/templatetags/transition_history.html')
def transition_history(asset):
    transitions_history = None
    if hasattr(asset, 'transitionshistory_set'):
        transitions_history = asset.transitionshistory_set.all()
    return {'transitions_history': transitions_history}


@register.inclusion_tag('assets/templatetags/collapsed_form.html')
def collapsed_form(form):
    """Render a collapsed form."""
    return {'form': form}


@register.inclusion_tag('assets/templatetags/object_list_search.html')
def object_list_search(object_instance, field):
    """Generate link to search releated fields objects. Currently work only
    with Support.
    """
    if isinstance(object_instance, Support):
        params = None
        mode = ASSET_TYPE2MODE.get(object_instance.asset_type)
        base_url = reverse('asset_search', args=(mode,))
        ids = getattr(object_instance, field).values_list('id', flat=True)
        if ids:
            params = ','.join(map(str, ids))
        url = '{}?id={}'.format(base_url, params)
    else:
        raise ValueError('%s is not supported' % object_instance)
    return {'url': url, 'field': field, 'show': params}


@register.filter(name='is_checkbox')
def is_checkbox(field):
    return field.field.widget.__class__.__name__ == CheckboxInput().__class__.__name__  # noqa


@register.inclusion_tag('assets/templatetags/multi_assign_widget.html')
def multi_assign_widget(empty_formset, formset):
    return {
        'empty_formset': empty_formset,
        'formset': formset,
        'assets_disabled': getattr(settings, 'ASSETS_DISABLED', False)
    }


@register.inclusion_tag('assets/templatetags/multi_assign_form.html')
def multi_assign_form(form, counter=''):
    return {'form': form, 'counter': counter}


@register.inclusion_tag(
    'assets/templatetags/mode_switch.html', takes_context=True,
)
def mode_switch(context):
    return {'mode': context['mode']}


@register.inclusion_tag('assets/templatetags/data_center_links.html')
def data_center_links(asset):
    return {
        'configuration_url': asset.get_configuration_url(),
        'visualization_url': asset.get_vizualization_url(),
    }


@register.inclusion_tag('assets/templatetags/transition_button.html')
def transition_button(asset=None, assets=None):
    both_false = not asset and not assets
    both_true = all([asset, assets])
    if both_false or both_true:
        raise ValueError('Please specify only one argument - asset or assets.')
    if asset:
        assets = [asset]

    return {
        'transitions': Transition.get_common_transitions_for_assets(assets),
        'asset_transitions_enabled': settings.ASSETS_TRANSITIONS.get('ENABLE'),
    }
