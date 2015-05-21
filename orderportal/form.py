"OrderPortal: Form pages."

from __future__ import unicode_literals, print_function, absolute_import

import logging

import tornado.web

import orderportal
from orderportal import constants
from orderportal import settings
from orderportal import utils
from orderportal import saver
from orderportal.fields import Fields
from orderportal.requesthandler import RequestHandler


class FormSaver(saver.Saver):
    doctype = constants.FORM

    def add_field(self):
        identifier = self.rqh.get_argument('identifier')
        if not constants.ID_RX.match(identifier):
            raise tornado.web.HTTPError(400, reason='invalid identifier')
        if self.rqh.get_argument('type') not in constants.TYPES_SET:
            raise tornado.web.HTTPError(400, reason='invalid type')
        fields = Fields(self.doc)
        if identifier in fields:
            raise tornado.web.HTTPError(409, reason='identifier already exists')
        self.changed['fields'] = fields.add(identifier, self.rqh)

    def update_field(self, identifier):
        fields = Fields(self.doc)
        if identifier not in fields:
            raise tornado.web.HTTPError(404, reason='no such field')
        self.changed['fields'] = fields.update(identifier, self.rqh)

    def copy_fields(self, form):
        "Copy all fields from the given form."
        if not hasattr(self.doc, 'fields'):
            self.doc['fields'] = []
        fields = Fields(self.doc)
        for field in form['fields']:
            fields.copy(field)
        self.changed['copied'] = "from {}".format(form['_id'])

    def delete_field(self, identifier):
        fields = Fields(self.doc)
        if identifier not in fields:
            raise tornado.web.HTTPError(404, reason='no such field')
        fields.delete(identifier)
        self.changed['fields'] = dict(identifier=identifier,
                                      action='deleted')


class FormMixin(object):
    "Mixin providing form-related methods."

    def is_editable(self, form):
        "Is the form editable? Checks status only."
        return form['status'] == constants.PENDING

    def check_editable(self, form):
        "Check if the form can be edited by the current user."
        self.check_admin()
        if not self.is_editable(form):
            raise tornado.web.HTTPError(409, reason='form is not pending')


class Forms(RequestHandler):
    "Forms list page."

    @tornado.web.authenticated
    def get(self):
        self.check_staff()
        view = self.db.view('form/modified', descending=True, include_docs=True)
        title = 'Recent forms'
        forms = [self.get_presentable(r.doc) for r in view]
        self.render('forms.html', title=title, forms=forms)


class Form(FormMixin, RequestHandler):
    "Form page."

    @tornado.web.authenticated
    def get(self, iuid):
        self.check_staff()
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.render('form.html',
                    title="Form '{}'".format(form['title']),
                    form=form,
                    is_editable=self.is_editable(form),
                    fields=Fields(form),
                    logs=self.get_logs(form['_id']))

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        if self.get_argument('_http_method', None) == 'delete':
            self.delete(iuid)
            return
        raise tornado.web.HTTPError(405, reason='POST only allowed for DELETE')

    @tornado.web.authenticated
    def delete(self, iuid):
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        self.delete_logs(form['_id'])
        self.db.delete(form)
        self.see_other(self.reverse_url('forms'))


class FormCreate(RequestHandler):
    "Page for creating an form."

    @tornado.web.authenticated
    def get(self):
        self.check_admin()
        self.render('form_create.html',
                    title='Create a new form')

    @tornado.web.authenticated
    def post(self):
        self.check_xsrf_cookie()
        self.check_admin()
        with FormSaver(rqh=self) as saver:
            saver['title'] = self.get_argument('title')
            saver['description'] = self.get_argument('description')
            saver['fields'] = []
            saver['status'] = constants.PENDING
            saver['owner'] = self.current_user['email']
            doc = saver.doc
        self.see_other(self.reverse_url('form_edit', doc['_id']))

    @tornado.web.authenticated
    def post(self):
        self.check_xsrf_cookie()
        self.check_admin()


class FormEdit(FormMixin, RequestHandler):
    "Page for editing an form."

    @tornado.web.authenticated
    def get(self, iuid):
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        self.render('form_edit.html',
                    title="Edit form '{}'".format(form['title']),
                    form=form)

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        with FormSaver(doc=form, rqh=self) as saver:
            saver['title'] = self.get_argument('title')
            saver['description'] = self.get_argument('description')
        self.see_other(self.reverse_url('form', form['_id']))


class FormFieldCreate(FormMixin, RequestHandler):
    "Page for creating a field in a form."

    @tornado.web.authenticated
    def get(self, iuid):
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        self.render('field_create.html',
                    title="Create field in form '{}'".format(form['title']),
                    form=form,
                    fields=Fields(form))

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        with FormSaver(doc=form, rqh=self) as saver:
            saver.add_field()
        self.see_other(self.reverse_url('form', form['_id']))


class FormFieldEdit(FormMixin, RequestHandler):
    "Page for editing or deleting a field in a form."

    @tornado.web.authenticated
    def get(self, iuid, identifier):
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        fields = Fields(form)
        try:
            field = fields[identifier]
        except KeyError:
            raise tornado.web.HTTPError(404, reason='no such field')
        self.render('field_edit.html',
                    title="Edit field '{}' in form '{}'".format(identifier,
                                                                form['title']),
                    form=form,
                    field=field)

    @tornado.web.authenticated
    def post(self, iuid, identifier):
        self.check_xsrf_cookie()
        if self.get_argument('_http_method', None) == 'delete':
            self.delete(iuid, identifier)
            return
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        with FormSaver(doc=form, rqh=self) as saver:
            saver.update_field(identifier)
        self.see_other(self.reverse_url('form', form['_id']))

    @tornado.web.authenticated
    def delete(self, iuid, identifier):
        form = self.get_entity(iuid, doctype=constants.FORM)
        self.check_editable(form)
        with FormSaver(doc=form, rqh=self) as saver:
            saver.delete_field(identifier)
        self.see_other(self.reverse_url('form', form['_id']))


class FormCopy(RequestHandler):
    "Make a copy of a form."

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        self.check_admin()
        form = self.get_entity(iuid, doctype=constants.FORM)
        with FormSaver(rqh=self) as saver:
            saver['title'] = "Copy of {}".format(form['title'])
            saver['description'] = form.get('description')
            saver.copy_fields(form)
            saver['status'] = constants.PENDING
            saver['owner'] = self.current_user['email']
            doc = saver.doc
        self.see_other(self.reverse_url('form_edit', doc['_id']))


class FormEnable(RequestHandler):
    "Enable making orders from the form."

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        self.check_admin()
        form = self.get_entity(iuid, doctype=constants.FORM)
        url = self.absolute_reverse_url('form', iuid)
        if form['status'] != constants.ENABLED:
            with FormSaver(doc=form, rqh=self) as saver:
                saver['status'] = constants.ENABLED
        self.see_other(url)


class FormDisable(RequestHandler):
    "Disable making orders from the form."

    @tornado.web.authenticated
    def post(self, iuid):
        self.check_xsrf_cookie()
        self.check_admin()
        form = self.get_entity(iuid, doctype=constants.FORM)
        url = self.absolute_reverse_url('form', iuid)
        if form['status'] != constants.DISABLED:
            with FormSaver(doc=form, rqh=self) as saver:
                saver['status'] = constants.DISABLED
        self.see_other(url)