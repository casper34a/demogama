# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime
from odoo.exceptions import UserError
import time
import logging
_logger = logging.getLogger(__name__)

_READONLY_STATES={'sale': [('readonly', True)]}

class SaleOrderQLS(models.Model):
    _inherit = "sale.order"

    type_pay                 = fields.Selection([('normal','Normal'),('plan_pagos','Plan de pagos')], default="plan_pagos",states=_READONLY_STATES)
    cuotas                   = fields.Integer(string="Cantidad de cuotas",states=_READONLY_STATES)
    vencimiento_primer_cuota = fields.Date(string="Vencimiento primer cuota",states=_READONLY_STATES)
    vencimiento_anticipo     = fields.Date(string="Vencimiento Anticipo",states=_READONLY_STATES)
    periocidad               = fields.Integer(string="Periocidad",states=_READONLY_STATES)
    anticipo                 = fields.Boolean(string="Anticipo",states=_READONLY_STATES)
    valor_anticipo           = fields.Float(string="Valor anticipado",states=_READONLY_STATES)
    valor_cuota              = fields.Float(string="Valor cuota", readonly=1)
    fecha_toma_indice        = fields.Date(string="Fecha toma indice")
    type_periodo             = fields.Selection([('day','Dias'),('month','Meses')], default='month', string="Tipo de periodo",states=_READONLY_STATES)
    coeficiente_id           = fields.Many2one('qls.indice.periodo',string="Indice periodo",states=_READONLY_STATES)

    def update_quotes_sales(self):
        orders = self.search([])
        for company in self.env['res.company'].search([]):
            company_env = self.with_context(force_company=company.id)
            orders = company_env.env['sale.order'].search([('state','=','sale'),('company_id','=',company.id)])
            for order in orders:
                if order.coeficiente_id:
                    order.calculate_indice_deuda()

    def calculate_indice_deuda(self):
        order           = self

        #BUSCO EL EL INDICE DEL MES ACTUAL CON RESPECTO AL INDICE SELECCIONADO EN LA ORDEN
        actual_indice       = self.coeficiente_id.indice_id.get_active_indice(self.coeficiente_id)

        i= 0
        if actual_indice and actual_indice.id != order.coeficiente_id.id and order.invoice_ids:

            #CALCULO LA DEUDA QUE GENERA EL INDICE ACTUAL


            #BUSCO FACTURAS GENERADAS POR LOS INDICES
            indice_deudas = order.invoice_ids.filtered(lambda i:i.from_coeficiente == True)

            if not indice_deudas:

                #SI NO HAYFACTURAS GENERADAS POR LOS INDICES, CREO 1 POR CADA CUOTA
                while i < self.cuotas:

                    invoice_related = order.invoice_ids.filtered(lambda inv: inv.quote == i+1)
                    if invoice_related.amount_residual:
                        total = ((invoice_related.amount_residual / order.coeficiente_id.base) * actual_indice.base) - invoice_related.amount_residual

                        product = self.env['product.product'].search([('id', '=', int(self.env['ir.config_parameter'].sudo().get_param('guiar.product_indice_id')))])

                        if not product:
                            raise Warning("Debe setear 'Producto para deuda indice' en las configuraciones de plan de pago")

                        Wizardinvoice = self.env['sale.advance.payment.inv'].create({'advance_payment_method': 'fixed',
                                                                                     'fixed_amount': total,
                                                                                     'product_id':product.id})

                        sale_line_obj   = Wizardinvoice.env['sale.order.line']
                        amount          = Wizardinvoice.fixed_amount
                        taxes           = Wizardinvoice.product_id.taxes_id.filtered(lambda r: not order.company_id or r.company_id == order.company_id)

                        if order.fiscal_position_id and taxes:
                            tax_ids = order.fiscal_position_id.map_tax(taxes).ids
                        else:
                            tax_ids = taxes.ids


                        context = {'lang': order.partner_id.lang}
                        so_line = sale_line_obj.create({
                            'name'          : ('Deuda por indice: %s %s/%s') % (actual_indice.indice_id.name,
                                                                                actual_indice.mes,
                                                                                actual_indice.anio
                                                                                ),
                            'price_unit'    : amount,
                            'product_uom_qty': 0.0,
                            'order_id'      : order.id,
                            'discount'      : 0.0,
                            'product_uom'   : Wizardinvoice.product_id.uom_id.id,
                            'product_id'    : Wizardinvoice.product_id.id,
                            'tax_id'        : [(6, 0, tax_ids)],
                            'is_downpayment': True,
                        })
                        del context

                    i+=1

                    if invoice_related.amount_residual:
                        invoice = Wizardinvoice._create_invoice(order, so_line,
                                                            amount,
                                                            invoice_date_due=invoice_related.invoice_date_due,
                                                            indice_id=actual_indice,journal_id=invoice_related.journal_id)
                    if invoice_related.amount_residual:
                        invoice.quote =  i

                return True

            else:
                for deuda_indice in indice_deudas:
                    # SI  HAY FACTURAS GENERADAS POR LOS INDICES, SI SON != QUE INDICE ACTUAL Y NO ESTA PAGADA
                    #AGREGO UNA LINEA DE AJUSTE POR INDICE A LA FACTURA
                    if not deuda_indice.invoice_line_ids.filtered(lambda i:i.indice_id.id  == actual_indice.id) \
                            and deuda_indice.invoice_payment_state != 'paid':

                        invoice_related = order.invoice_ids.filtered(lambda inv: inv.quote == deuda_indice.quote
                                                                                 and inv.id !=deuda_indice.id)
                        total           = ((invoice_related.amount_residual / order.coeficiente_id.base) * actual_indice.base)\
                                          - invoice_related.amount_residual

                        total_add       = total - deuda_indice.amount_residual

                        product = self.env['product.product'].search([('id', '=', int(
                            self.env['ir.config_parameter'].sudo().get_param('guiar.product_indice_id')))])

                        if not product:
                            raise Warning(
                                "Debe setear 'Producto para deuda indice' en las configuraciones de plan de pago")


                        Wizardinvoice = self.env[
                            'sale.advance.payment.inv'].create(
                            {'advance_payment_method': 'fixed',
                             'fixed_amount': total_add,'product_id': product.id })

                        if Wizardinvoice.product_id.type != 'service':
                            raise UserError(
                                ("Los productos seteados en la configuracion de plan de pago deben de ser de tipo 'Servicio'."))

                        sale_line_obj = Wizardinvoice.env['sale.order.line']
                        amount = Wizardinvoice.fixed_amount
                        taxes = Wizardinvoice.product_id.taxes_id.filtered(lambda
                                                                               r: not order.company_id or r.company_id == order.company_id)

                        if order.fiscal_position_id and taxes:
                            tax_ids = order.fiscal_position_id.map_tax(taxes).ids
                        else:
                            tax_ids = taxes.ids


                        so_line = sale_line_obj.create({
                            'name': ('Deuda por indice: %s %s/%s') % (actual_indice.indice_id.name,
                                                                      actual_indice.mes,
                                                                      actual_indice.anio
                                                                    ),
                            'price_unit': amount,
                            'product_uom_qty': 0.0,
                            'order_id': order.id,
                            'discount': 0.0,
                            'product_uom': Wizardinvoice.product_id.uom_id.id,
                            'product_id': Wizardinvoice.product_id.id,
                            'tax_id': [(6, 0, tax_ids)],
                            'is_downpayment': True,
                        })


                        deuda_indice.invoice_line_ids = [(0, 0, {'name':  ('Deuda por indice: %s %s/%s') % (actual_indice.indice_id.name,
                                                                      actual_indice.mes,
                                                                      actual_indice.anio
                                                                    ),
                                                                 'price_unit': amount,
                                                                 'quantity': 1.0,
                                                                 'product_id': so_line.product_id.id,
                                                                 'product_uom_id': so_line.product_uom.id,
                                                                 'tax_ids': [(6, 0, so_line.tax_id.ids)],
                                                                 'sale_line_ids': [(6, 0, [so_line.id])],
                                                                 'analytic_tag_ids': [(6, 0, so_line.analytic_tag_ids.ids)],
                                                                 'analytic_account_id': order.analytic_account_id.id or False,
                                                                 'indice_id':actual_indice.id})]
                return True

