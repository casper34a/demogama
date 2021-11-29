from odoo import fields, models, api
import logging
from odoo.tools.safe_eval import safe_eval
from itertools import groupby
from datetime import datetime
from odoo.exceptions import UserError, ValidationError, Warning
_logger = logging.getLogger(__name__)


class ResCompanyInterestQS(models.Model):
    _inherit = 'res.company.interest'
    _description = 'Description'

    quote_interest = fields.Boolean(string="Regla para plan de pagos",default=False)

    receivable_account_ids = fields.Many2many(
        'account.account',
        string='Cuentas a Cobrar',
        help='Cuentas a Cobrar que se tendrán en cuenta para evaular la deuda',
        domain="[('user_type_id.type', '=', 'receivable'),"
        "('company_id', '=', company_id)]",
    )

    @api.onchange('quote_interest')
    def set_domain_quote(self):
        if self.quote_interest:
            domain_lines = [
                            ('account_id.reconcile', '=', True),
                            ('reconciled', '=', False),
                            ('full_reconcile_id', '=', False),
                            ('company_id', '=', self._origin.company_id.id),
                            ('move_id.state', '=', 'posted'),('move_id.quote', '>', 0)]

            # I search all move that it can be cinciled
            account_move_lines = self.env['account.move.line'].search(domain_lines)
            self.domain = [('id','in',account_move_lines.ids)]

    def create_invoices(self, to_date):
        if self.quote_interest:
            self.ensure_one()

            # Format date to customer langague
            # For some reason there is not context pass, not lang, so we
            # force it here
            lang_code = self.env.context.get('lang', self.env.user.lang)
            lang = self.env['res.lang']._lang_get(lang_code)
            date_format = lang.date_format
            to_date_format = fields.Date.from_string(
                to_date).strftime(date_format)

            self.set_domain_quote()
            journal = self.env['account.journal'].search([
                ('type', '=', 'sale'),
                ('company_id', '=', self.company_id.id)], limit=1)

            move_line_domain = [
                ('full_reconcile_id', '=', False)
            ]

            # Check if a filter is set
            if self.domain:
                move_line_domain += safe_eval(self.domain)

            move_line = self.env['account.move.line']


            lines = move_line.search(move_line_domain)

            sorted_form_origin_file = lines.sorted(lambda move: move.move_id.invoice_origin)

            lines_gropng_map,keys = self.get_grouping_lines(sorted_form_origin_file.filtered(lambda s:s.move_id.invoice_date_due <datetime.strptime(to_date, '%Y-%m-%d').date()))


            self = self.with_context(mail_notrack=True, prefetch_fields=False)



            for key in keys:
                line = lines_gropng_map[key]
                debt = sum(l.amount_residual if not l.move_id.from_interest else 0 for l in line)

                if not debt or debt <= 0.0:
                    continue

                partner_id = line[0].partner_id
                move_id = line[0].move_id

                order_id = self.env['sale.order'].search([('name', '=', move_id.invoice_origin)])

                partner = self.env['res.partner'].browse(partner_id.id)
                invoice_vals = self._prepare_interest_invoice(
                    partner, debt, to_date, journal, quote=move_id.quote, invoice_origin= move_id.invoice_origin)

                #Creating line for order
                analytic_tag_ids = []
                for ord_line in order_id.order_line:
                    analytic_tag_ids = [(4, analytic_tag.id, None) for
                                        analytic_tag in ord_line.analytic_tag_ids]

                sale_line_obj       = self.env['sale.order.line']
                so_line_values      = self._prepare_so_line(order_id, analytic_tag_ids, debt)
                so_line             = sale_line_obj.create(so_line_values)


                invoice = self.env['account.move'].search([('quote','=',move_id.quote),('from_interest','=',True),
                                                           ('invoice_origin','=',move_id.invoice_origin)])
                # we send document type for compatibility with argentinian
                # invoices
                if not invoice:
                    #Si no hay factura creo una nueva
                    invoice = self.env['account.move'].with_context(
                        internal_type='debit_note').create(invoice_vals).with_user(self.env.uid)

                    lines = self._prepare_interest_invoice_line(
                        invoice, partner, debt, to_date_format)

                    lines.update({'sale_line_ids': [(6, 0, [so_line.id])],})

                    invoice.invoice_line_ids = [(0, 0, lines)]
                    invoice.from_interest = True
                    # update amounts for new invoice
                    if self.automatic_validation:
                        try:
                            invoice.action_post()
                        except Exception as e:
                            _logger.error(
                                "Something went wrong "
                                "creating interests invoice: {}".format(e))

                    else:
                        return super().create_invoices(to_date)

                else:
                    # SI  HAY FACTURAS GENERADAS POR LOS INDICES, SI SON != QUE INDICE ACTUAL Y NO ESTA PAGADA
                    #AGREGO UNA LINEA DE AJUSTE POR INDICE A LA FACTURA

                    invoice_related = order_id.invoice_ids.filtered(lambda inv: inv.quote == invoice.quote
                                                                             and inv.id !=invoice.id)
                    total           = sum(inv.amount_residual for inv in invoice_related)
                    total_add       = total
                    product = self.interest_product_id
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
                                                                           r: not order_id.company_id or r.company_id == order_id.company_id)
                    if order_id.fiscal_position_id and taxes:
                        tax_ids = order_id.fiscal_position_id.map_tax(taxes).ids
                    else:
                        tax_ids = taxes.ids
                    so_line = sale_line_obj.create({
                        'name': ('Intereses') ,
                        'price_unit': amount,
                        'product_uom_qty': 0.0,
                        'order_id': order_id.id,
                        'discount': 0.0,
                        'product_uom': Wizardinvoice.product_id.uom_id.id,
                        'product_id': Wizardinvoice.product_id.id,
                        'tax_id': [(6, 0, tax_ids)],
                        'is_downpayment': True,
                    })
                    lines = self._prepare_interest_invoice_line(
                        invoice, partner, total_add, to_date_format)
                    invoice.invoice_line_ids = [(0, 0, lines)]

    def _prepare_interest_invoice(self, partner, debt, to_date, journal, quote=False, invoice_origin=False):
        res = super(ResCompanyInterestQS,self)._prepare_interest_invoice(partner, debt, to_date, journal)
        if self.quote_interest:

            journal_id = self.company_id.jorunal_interes_id.id
            res.update({'journal_id':journal_id,
                        'quote':quote,
                        'invoice_origin':invoice_origin,
                        'name':self.env['ir.sequence'].next_by_code('invoice.interest')
                    })

            return res

        else:
            return res

    def _prepare_so_line(self,order_id, analytic_tag_ids, debt):
        taxes = self.interest_product_id.taxes_id.filtered(lambda
                                                      r: not order_id.company_id or r.company_id == order_id.company_id)
        if order_id.fiscal_position_id and taxes:
            tax_ids = order_id.fiscal_position_id.map_tax(taxes,
                                                       self.interest_product_id,
                                                       order_id.partner_shipping_id).ids
        else:
            tax_ids = taxes.ids

        context = {'lang': order_id.partner_id.lang}
        so_values = {
            'name': 'Intereses',
            'price_unit': debt,
            'product_uom_qty': 0.0,
            'order_id': order_id.id,
            'discount': 0.0,
            'product_uom': self.interest_product_id.uom_id.id,
            'product_id': self.interest_product_id.id,
            'analytic_tag_ids': analytic_tag_ids,
            'tax_id': [(6, 0, tax_ids)],
        }

        return so_values

    def get_grouping_lines(self,sorted_form_origin_file):
        res = {}
        res_map_key_list = []
        for k, groups_for_invoice in groupby(sorted_form_origin_file, lambda move: move.move_id.invoice_origin):
            for invoice in groups_for_invoice:
                origen = invoice.move_id.invoice_origin
                quote = invoice.move_id.quote
                key = origen + "-" +str(quote)
                if not res.get(key, False):
                    res.setdefault(key, [])
                    res_map_key_list.append(key)
                res[key].append(invoice)

        return res,res_map_key_list