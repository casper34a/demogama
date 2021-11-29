# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError,Warning
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import logging
_logger = logging.getLogger(__name__)

class SaleAdvancePaymentInvQSL(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    advance_payment_method = fields.Selection(selection_add=[('quotes_plan', 'Plan de cuotas')], default='quotes_plan')

    journal_add_id  = fields.Many2one('account.journal',string="Diario")

    def get_amount_and_name(self,order):
        if self.advance_payment_method == 'percentage':
            if all(self.product_id.taxes_id.mapped('price_include')):
                amount = order.amount_total * self.amount / 100
            else:
                amount = order.amount_untaxed * self.amount / 100
            name = _("Cuota %s") % (str(self.amount))

        return amount, name

    def get_amount_and_name_multiples(self, order):
        if all(self.product_id.taxes_id.mapped('price_include')):
            amount = order.amount_total
        else:
            amount = order.amount_untaxed
        name = _("Cuota %s") % (str(self.amount))

        return amount, name

    def create_invoices(self):
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        #region AGREGADO POR QUILSOFT
        if self.advance_payment_method == 'quotes_plan' and len(sale_orders) == 1:
            aux_first_quote         = True
            unique_order            = sale_orders[0]
            qty_invoce              = unique_order.cuotas
            anticipo                = unique_order.valor_anticipo if unique_order.anticipo else 0
            amount_real             = self.get_amount_and_name_multiples(unique_order)[0]
            max_amount_x_invoice    = float((amount_real - anticipo)/qty_invoce)

            product= self.env['product.product'].search([('id','=',int(self.env['ir.config_parameter'].sudo().get_param('guiar.product_quote_id')))])

            if not product:
                raise Warning("Debe setear 'Producto para cuota' en las configuraciones de plan de pago")
            if not sale_orders[0].coeficiente_id:
                raise Warning("Para facturas de plan de cuotas necesita tener seteado un indice.")

            self.product_id =product.id

            sale_line_obj = self.env['sale.order.line']

            for order in sale_orders:

                #EN CASO  DE QUE LA CANTIDAD TOTAL DE LA ORDEN DIVIDO LA CANTIDAD DE FACTURAS SEA MAYOR
                #AL MAXIMO PERMITIDO, HAGO UNA FACTURA MAS
                if qty_invoce >0:

                    total_amount_invoices = max_amount_x_invoice

                    i=0 if unique_order.anticipo else 1
                    while i < qty_invoce:
                        amount, name = total_amount_invoices,_("Deposito de %s%%") % (str(total_amount_invoices))
                        if self.product_id.invoice_policy != 'order':
                            raise UserError(
                                _('The product used to invoice a down payment should have an invoice policy set to "Ordered quantities". Please update your deposit product to be able to create a deposit invoice.'))
                        if self.product_id.type != 'service':
                            raise UserError(
                                _("Los productos seteados en la configuracion de plan de pago deben de ser de tipo 'Servicio'."))
                        taxes = self.product_id.taxes_id.filtered(lambda
                                                                      r: not order.company_id or r.company_id == order.company_id)
                        if order.fiscal_position_id and taxes:
                            tax_ids = order.fiscal_position_id.map_tax(taxes,
                                                                       self.product_id,
                                                                       order.partner_shipping_id).ids
                        else:
                            tax_ids = taxes.ids

                        analytic_tag_ids = []
                        for line in order.order_line:
                            analytic_tag_ids = [(4, analytic_tag.id, None) for
                                                analytic_tag in line.analytic_tag_ids]

                        so_line_values      = self._prepare_so_line(order, analytic_tag_ids, tax_ids, amount)

                        so_line             = sale_line_obj.create(so_line_values)

                        order.valor_cuota   = amount
                        #CALCULO LA SIGUIENTE FECHA DE VENCIMIENTO
                        fecha_vencimiento   = unique_order.vencimiento_primer_cuota if aux_first_quote else fecha_vencimiento
                        days_in_month       = relativedelta(months=unique_order.periocidad) if order.type_periodo == 'month' else relativedelta(days=unique_order.periocidad)
                        fecha_vencimiento   = (fecha_vencimiento  + days_in_month) if not aux_first_quote else fecha_vencimiento

                        quote_invoice = self._create_invoice(order, so_line, amount, invoice_date_due=fecha_vencimiento, journal_id=self.journal_add_id)

                        aux_first_quote = False
                        i +=1
                        quote_invoice.quote = (i) if unique_order.anticipo else i-1
                        quote_invoice.action_post()

                    final_invoice = sale_orders._create_invoices(final=True)
                    if not unique_order.anticipo:
                        final_invoice.quote = i

                    final_invoice.journal_id        = self.journal_add_id.id
                    final_invoice.invoice_date_due  = unique_order.vencimiento_anticipo if unique_order.anticipo else fecha_vencimiento + days_in_month
                    final_invoice.action_post()
                else:
                    sale_orders._create_invoices(final=False)
            sale_orders[0].calculate_indice_deuda()
            if self._context.get('open_invoices', False):
                return sale_orders.action_view_invoice()

        #endregion

        elif self.advance_payment_method == 'delivered':
            sale_orders._create_invoices(final=self.deduct_down_payments)
        else:
            # Create deposit product if necessary
            if not self.product_id:
                vals = self._prepare_deposit_product()
                self.product_id = self.env['product.product'].create(vals)
                self.env['ir.config_parameter'].sudo().set_param('sale.default_deposit_product_id', self.product_id.id)

            sale_line_obj = self.env['sale.order.line']
            for order in sale_orders:
                amount, name = self._get_advance_details(order)

                if self.product_id.invoice_policy != 'order':
                    raise UserError(_('The product used to invoice a down payment should have an invoice policy set to "Ordered quantities". Please update your deposit product to be able to create a deposit invoice.'))
                if self.product_id.type != 'service':
                    raise UserError(_("The product used to invoice a down payment should be of type 'Service'. Please use another product or update this product."))
                taxes = self.product_id.taxes_id.filtered(lambda r: not order.company_id or r.company_id == order.company_id)
                if order.fiscal_position_id and taxes:
                    tax_ids = order.fiscal_position_id.map_tax(taxes, self.product_id, order.partner_shipping_id).ids
                else:
                    tax_ids = taxes.ids
                analytic_tag_ids = []
                for line in order.order_line:
                    analytic_tag_ids = [(4, analytic_tag.id, None) for analytic_tag in line.analytic_tag_ids]

                so_line_values = self._prepare_so_line(order, analytic_tag_ids, tax_ids, amount)
                so_line = sale_line_obj.create(so_line_values)
                self._create_invoice(order, so_line, amount)
        if self._context.get('open_invoices', False):
            return sale_orders.action_view_invoice()
        return {'type': 'ir.actions.act_window_close'}

    def _create_invoice(self, order, so_line, amount, invoice_date_due=False,indice_id=False, journal_id=False):
        if (self.advance_payment_method == 'percentage' and self.amount <= 0.00) or (self.advance_payment_method == 'fixed' and self.fixed_amount <= 0.00):
            raise UserError(_('The value of the down payment amount must be positive.'))

        if self.advance_payment_method!='quotes_plan':
            amount, name = self._get_advance_details(order)
        else:
            amount, name = amount,_("Pago anticipado de %s") % (str(amount))

        if indice_id:
            invoice_vals = self._prepare_invoice_values_with_indice(order, name, amount, so_line, indice_id=indice_id)
        else:
            invoice_vals = self._prepare_invoice_values(order, name, amount, so_line)

        if order.fiscal_position_id:
            invoice_vals['fiscal_position_id'] = order.fiscal_position_id.id

        if invoice_date_due:
            invoice_vals['invoice_date_due'] = invoice_date_due

        invoice = self.env['account.move'].sudo().create(invoice_vals).with_user(self.env.uid)
        invoice.message_post_with_view('mail.message_origin_link',
                    values={'self': invoice, 'origin': order},
                    subtype_id=self.env.ref('mail.mt_note').id)

        if indice_id:
            invoice.from_coeficiente = True

        if journal_id:
            invoice.journal_id = journal_id.id

        if self.advance_payment_method=='fixed':
            if  indice_id:
                invoice.indice_id = indice_id.id
                invoice.action_post()



        return invoice

    def _prepare_invoice_values_with_indice(self, order, name, amount, so_line, indice_id=False):
        res = super()._prepare_invoice_values(order, name, amount, so_line)
        if indice_id:
            res['invoice_line_ids'][0][2]['indice_id']  = indice_id.id
            res['invoice_line_ids'][0][2]['name']       = so_line.name
        return res