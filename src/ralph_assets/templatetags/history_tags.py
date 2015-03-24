# -*- coding: utf-8 -*-
"""Templatetags specific for ralph_assets"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from django import template
from django.utils.translation import ugettext_lazy as _

from ralph_assets.history.models import History


register = template.Library()


def get_context(obj, history, limit, full_history_button, title,
                show_field_name=True):
    return {
        'full_history_button': full_history_button,
        'history_for_model_url': History.get_history_url_for_object(obj),
        'history_title': title,
        'limit': limit,
        'history': history[:limit] if history else None,
        'show_field_name': show_field_name,
    }


@register.inclusion_tag('assets/templatetags/short_history.html')
def short_history(obj, limit=5, full_history_button=True):
    """Render a short history table."""
    if not obj:
        return {}
    history = obj.get_history()
    return get_context(
        obj,
        history.order_by('-date'),
        limit,
        full_history_button,
        _('Short history'),
    )


@register.inclusion_tag('assets/templatetags/short_history.html')
def status_history(obj, limit=5, full_history_button=True):
    """Render a short history table only for status changes."""
    if not obj:
        return {}
    history = obj.get_history(field_name='status')
    return get_context(
        obj,
        history.order_by('-date'),
        limit,
        full_history_button,
        _('Status history'),
        False,
    )
