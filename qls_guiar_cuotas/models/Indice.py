# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime,date
from odoo.exceptions import ValidationError, Warning
import logging
_logger = logging.getLogger(__name__)

class Indice(models.Model):
    _name = 'qls.indice'
    _description = 'Indice'
    _sql_constraints = [
        ('value_name_indice_uniq', 'unique (name)', 'Ya existe un indice con este nombre')
    ]

    name = fields.Char(string="Nombre del indice", help="Por ejemplo: 'Indice CAC'")

    periodo_ids = fields.One2many('qls.indice.periodo','indice_id', string="Periodos")

    def get_active_indice(self, coeficinete_id):

        indices_that_year = self.periodo_ids.filtered(lambda periodo: str(periodo.anio) > str(coeficinete_id.anio))

        indices_today = self.periodo_ids.filtered(lambda periodo: str(periodo.anio) == str(coeficinete_id.anio))

        if indices_that_year:
            #SI HAY INDICES DE UN AÑO MAS NUEVO DEVUELVO EL ULTIMO
            for indice in indices_that_year.sorted(key=lambda i:int(i.mes),reverse=True):
                last_indice= indice
                break
        else:
            # SI HAY INDICES DEL MISMO AÑO QUE EL INDICE SELECCIONADO
            for indice in indices_today.sorted(key=lambda i:int(i.mes),reverse=True):
                last_indice= indice
                break
        return last_indice

    def get_last_indice(self):
        currentdate = datetime.today()

        indice = self.periodo_ids.sorted(lambda pm: pm.anio, reverse=True)

        return indice

class IndicePeriodo(models.Model):
    _name = 'qls.indice.periodo'
    _order = "anio"
    _description = 'Indice Periodo'
    _sql_constraints = [
        ('val_anio_mes_indice_id', 'unique (mes,anio,indice_id)', 'Ya existe este indice para este periodo.')
    ]
    anio                = fields.Integer(string =u"Año",
                                      required=True, size=4,
                                      default =lambda self: str(date.today().year))
    mes                 = fields.Selection([(str(num), str(num)) for num in range(1, 13)],
                                  string=u"Mes",
                                  size=2,
                                  required=True,
                                  default=str(date.today().month))
    name                = fields.Char(string="Nombre",compute="set_periodo_name",
                                        store=True)

    base                = fields.Float(string="Monto Base")
    porcentaje_variacion= fields.Float(string="Variacion", compute='set_variacion')
    indice_id           = fields.Many2one('qls.indice', string="Indice",required=True)

    @api.depends('mes', 'anio','indice_id')
    def set_periodo_name(self):
        if self.mes and self.anio and self.indice_id:
            self.name = self.mes + '/' + str(self.anio)+ "-" + self.indice_id.name

    @api.depends('anio','mes','indice_id')
    def set_variacion(self):
        """Calcula el porcentaje de variacion entre este indice y un indice anterior"""
        if self.anio and self.mes and self.indice_id and self.id:
            #Todos los indices menores al año actual y ordenados
            sorted_last_indices = self.search([('anio','<=',self.anio),
                                               ('indice_id','=',self.indice_id.id),
                                               ('id','!=',self.id)], order='mes desc')
            last_indice = []
            if sorted_last_indices:

                #Indices que son de este año y que son de meses anteriores con respecto del indice actual
                before_year_indices = sorted_last_indices.filtered(lambda i: i.anio== self.anio and int(i.mes)< int(self.mes))

                #Indices de otrosaños
                lasts_year_indices= sorted_last_indices.filtered(lambda i: i.anio< self.anio)

                # HAGO ESTOS FOR POR QUE POR ALGUNA RAZON LAS LISTAS SE ME DESACOMODAN EN UNA VARIABLE
                for sorted in before_year_indices.sorted(key=lambda i:int(i.mes),reverse=True):
                    last_indice= sorted
                    break

                if not before_year_indices and lasts_year_indices:
                    for sorted in lasts_year_indices.sorted(key=lambda i: int(i.mes), reverse=True):
                        last_indice         = sorted
                        break

                if last_indice :
                    #formula % de variacion (v2-v1)/v1 *100
                    self.porcentaje_variacion = ((self.base - last_indice[0].base)/last_indice[0].base)*100
                else:
                    self.porcentaje_variacion = 0
            else:
                self.porcentaje_variacion=0
        else:
            self.porcentaje_variacion =0

    @api.constrains('base')
    def constrains_monto_base(self):
        if self.base <=0.0:
            raise Warning("Atención, el 'Monto Base' debe ser mayor a 0")


    def get_last_indice(self):
        sorted_last_indices = self.search([('anio', '<=', self.anio),
                                           ('indice_id', '=',self.indice_id.id),
                                           ('id', '!=', self.id)], order='mes desc')

        last_indice = []
        if sorted_last_indices:

            # Indices que son de este año y que son de meses anteriores con respecto del indice actual
            before_year_indices = sorted_last_indices.filtered(
                lambda i: i.anio == self.anio and int(i.mes) < int(self.mes))

            # Indices de otrosaños
            lasts_year_indices = sorted_last_indices.filtered(
                lambda i: i.anio < self.anio)

            # HAGO ESTOS FOR POR QUE POR ALGUNA RAZON LAS LISTAS SE ME DESACOMODAN EN UNA VARIABLE
            for sorted in before_year_indices.sorted(key=lambda i: int(i.mes),
                                                     reverse=True):
                last_indice = sorted
                break

            if not before_year_indices and lasts_year_indices:
                for sorted in lasts_year_indices.sorted(
                        key=lambda i: int(i.mes), reverse=True):
                    last_indice = sorted
                    break

        return last_indice
