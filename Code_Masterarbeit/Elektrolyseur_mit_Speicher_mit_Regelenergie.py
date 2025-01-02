from oemof import solph
import pandas as pd
import numpy as np
import pyomo.environ as po
import random
import datetime as dt

##################### einzugebende Parameter #####################
num_tsteps = 8760 #Anzahl der Zeitschritte
number_tsteps = num_tsteps
window_size = 100
c_h2_virtual = -65 #virtueller H2-Preis €/MWh
c_h2 = 0 #angenommener H2-Preis für freien H2-Markt €/MWh
c_heat = 0#[-70]*8760
c_oxygen = 0#[-0.6]*8760

power_ely = 20  # Beispiel-Leistung des Elektrolyseurs in MW
investment_cost_ely = 1000  # Beispiel-Investitionskosten in Euro/kW
number_years = 20 #Abschreibungsdauer in Jahren
interest_rate = 0.06 #Zinssatz für die Abschreibung
w = 0.04 #Kosten für Wartung, Betrieb, Versicherung

power_h2_storage = 150 #MWh
investment_cost_h2_storage = 30 #€/kWh
power_el_storage = 5 #MWh
investment_cost_el_storage = 300 #€/kWh

investment_cost_total = (investment_cost_ely * power_ely + investment_cost_h2_storage * power_h2_storage + investment_cost_el_storage * power_el_storage) * 1000

#annualized capex
a = (((1+interest_rate)**number_years)*interest_rate)/(((1+interest_rate)**number_years)-1)
annualized_cost = investment_cost_total * (a+w)



#Daten Teillastverahlten
eta_h2_min = 0.60 #efficiency at P_in_min
eta_h2_max = 0.50 #efficiency at P_in_max
P_in_min = 2
P_in_max = 20

#slope und offset for part-load behavior hydrogen, heat, oxygen
slope_h2, offset_h2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min, eta_at_max=0.5, eta_at_min=0.6)

slope_heat, offset_heat = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min, eta_at_max=0.5, eta_at_min=0.4)


#Daten Teillastverahlten
eta_h2_min_2 = 0 #efficiency at P_in_min
eta_h2_max_2 = 0.60 #efficiency at P_in_max
P_in_min_2 = 0
P_in_max_2 = 2

#slope und offset for part-load behavior hydrogen, heat, oxygen
slope_h2_2, offset_h2_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2, eta_at_max=eta_h2_max_2, eta_at_min=eta_h2_min_2)

slope_heat_2, offset_heat_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2, eta_at_max=0.4, eta_at_min=1)



#sonstige Variablen
min_rate = 1/power_ely #Rate damit minimale Regelenergie 5MW ist
el_storage_capacity = 5
el_storage_input_flow = 5
el_storage_output_flow = 5
el_storage_loss_rate = 0.002 #loss rate per hour
el_storage_variable_costs = 0
el_storage_initial_storage_level = 0
hydrogen_storage_capacity = 150
hydrogen_storage_input_flow = 50
hydrogen_storage_output_flow = 50
hydrogen_storage_variable_costs = 0
hydrogen_storage_loss_rate = 0.002
hydrogen_storage_initial_storage_level = 0
p_demand = -10 #Preis für den H2 an feste Abnehmer verkauft wird [€/MWh]

##################### einlesen von Zeitreihen #####################

#Strompreisdaten
konzessionsabgabe = 1.1 # €/MWh
umlage_strom_nev = 4 # €/MWh
umsatzsteuer = 0.19 # in %
ppa = 50 # €/MWh
c_el = pd.read_excel("/Users/lucajahner/Documents/Masterarbeit/Modell/Daten/DayAhead_Boersenstrompreis_stuendlich_2019_energy_charts.xlsx") #DayAhead_Börsenstrompreise_stündlich_2023_energy_charts.xlsx
c_el = c_el["Preis (EUR/MWh)"].iloc[:]
c_el = (c_el + konzessionsabgabe + umlage_strom_nev) * (1+umsatzsteuer) # Strompreis inkl. Umlagen und Abgaben
#c_el = (ppa + konzessionsabgabe + umlage_strom_nev) * (1+umsatzsteuer)
#c_el = pd.Series([c_el]*8760)

#Regelenergiedaten
affr = pd.read_excel("/Users/lucajahner/Documents/Masterarbeit/Modell/Daten/Regelenergie_affr_pos_neg_stuendliche_Daten_2019_smard.xlsx") #Regelenergie_affr_pos_neg_stündliche_Daten_2023_bis_Juli_smard.xlsx
demand_pos_affr = affr["Vorgehaltene Menge (+) [MW]"]
demand_neg_affr = affr["Vorgehaltene Menge (-) [MW]"]
lp_pos_affr = affr["Leistungspreis (+) [€/MW]"].iloc[:]
lp_neg_affr = affr["Leistungspreis (-) [€/MW]"].iloc[:]#num_tsteps

abfrage_affr = pd.read_excel("/Users/lucajahner/Documents/Masterarbeit/Modell/Daten/Aktivierte_aFRR_2019_qualitaetsgesichert_stuendliche_Daten.xlsx") #Aktivierte_aFRR_2023_qualitaetsgesichert_stündliche_Daten.xlsx
b_pos = abfrage_affr["b_pos"].iloc[:num_tsteps]
b_neg = abfrage_affr["b_neg"].iloc[:num_tsteps]

#Berechnung Arbeitspreise

ap_neg_affr = c_el+0.55*c_h2_virtual
ap_neg_affr = [x if x >= 0 else 0 for x in ap_neg_affr] #bei den Werten die kleiner 0 sind lohnt es sich bereits zu produzieren, heißt der AP ist irrelevant um wirtschaftlich zu sein
ap_neg_affr = pd.Series(ap_neg_affr) #positive Werte - bei variable_cost muss ein minus davor

ap_pos_affr = c_el+0.55*c_h2_virtual #bei den Werten die kleiner 0 sind lohnt es sich eh nicht zu produzieren, daher wird der AP auf 0 gesetzt
ap_pos_affr = [x if x <= 0 else 0 for x in ap_pos_affr]
ap_pos_affr = pd.Series(ap_pos_affr)
p_pos_affr_gesamt = [-lp_pos_affr[i] + b_pos[i] * ap_pos_affr[i] for i in range(num_tsteps)]


random.seed(42)
demand_h2 = [random.randint(0, 10) for _ in range(8760)]

opt1_input_ely_1_1 = []
opt1_input_ely_1_2 = []
input_ely_1_1 = []
output_ely_1_1 = []
input_ely_1_2 = []
output_ely_1_2 = []
nachfrage = []
vorhalten_neg_affr = []
abrufen_neg_affr = []
hydrogen_neg_affr = []
neg_signal = []
vorhalten_pos_affr = []
abrufen_pos_affr = []
pos_signal = []
storage_content_h2 = []
input_h2_storage = []
input2_h2_storage = []
output_h2_storage = []
output2_h2_storage = []
storage_content_el = []
input_el_storage = []
input2_el_storage = []
output_el_storage = []
output2_el_storage = []
time = []
strombezug=[]
menge_abwärme = []
menge_sauerstoff=[]
menge_wasser=[]

el_storage_initial_storage_level = 0
hydrogen_storage_initial_storage_level = 0

electricity_flow_ely2_1 = 0
electricity_flow_ely2_2 = 0
electricity_flow_ely3_1 = 0
electricity_flow_ely3_2 = 0


start_time = dt.datetime(2019, 1, 1, 0, 0,
                         0)  # evtl. brauch ich das gar nicht hier, da nochmal später im Code vorhanden

for n in range(num_tsteps):

    start_idx = n
    end_idx = min(n + window_size, num_tsteps)
    c_el_angepasst = c_el.iloc[start_idx:end_idx].reset_index(drop=True)
    lp_pos_affr_angepasst = lp_pos_affr.iloc[start_idx:end_idx].reset_index(drop=True)
    lp_neg_affr_angepasst = lp_neg_affr.iloc[start_idx:end_idx].reset_index(drop=True)
    demand_h2_angepasst = demand_h2[start_idx:end_idx]

    # Hier wird der Startzeitpunkt in jeder Iteration um eine Stunde nach hinten verschoben - passend zu den Listen
    start_time = dt.datetime(2019, 1, 1, 0, 0) + dt.timedelta(hours=n)
    # definition of time index
    # datetime_index = solph.create_time_index(year=2019, number=number_tsteps-n, start=start_time)#number_tsteps
    datetime_index = solph.create_time_index(year=2019, number=end_idx - start_idx, start=start_time)

    es2 = solph.EnergySystem(timeindex=datetime_index, infer_last_interval=False)

    # Definition Bus-Components
    b_el = solph.Bus("electricity bus")
    b_h2 = solph.Bus("hydrogen bus")
    b_heat = solph.Bus("heat bus")
    b_o2 = solph.Bus("oxygen bus")
    b_h2o = solph.Bus("water bus")

    b_el_neg_affr_virt = solph.Bus("neg affr virt electricity bus")
    b_h2_neg_affr_virt = solph.Bus("neg affr virt hydrogen bus")
    b_el_pos_affr_virt = solph.Bus("pos affr virt electricity bus")
    b_h2_pos_affr_virt = solph.Bus("pos affr virt hydrogen bus")

    ##### Definition der Komponenten #####

    # electricity source for basic hydrogen demand
    source_el = solph.components.Source(
        "electricity import",
        outputs={
            b_el: solph.Flow(
                variable_costs=c_el_angepasst
            )
        }
    )

    source_h2o = solph.components.Source(
        "water import",
        outputs={
            b_h2o: solph.Flow(
                variable_costs=0.0015  # €/l Wasser
            )
        }
    )

    source_o2 = solph.components.Source(
        "oxygen import",
        outputs={
            b_o2: solph.Flow(
            )
        }
    )

    source_el_neg_affr_virt = solph.components.Source(
        "electricity neg affr virt",
        outputs={
            b_el_neg_affr_virt: solph.Flow(
                nominal_value=power_ely,
                min=min_rate,
                nonconvex=solph.NonConvex(
                )
            )
        }
    )

    source_el_pos_affr_virt = solph.components.Source(
        "electricity pos affr virt",
        outputs={
            b_el_pos_affr_virt: solph.Flow(
                nominal_value=power_ely,
                min=min_rate,
                nonconvex=solph.NonConvex(

                )
            )
        }
    )

    # Sink for fix haydrogen demand via contract
    sink_h2_demand = solph.components.Sink(
        "hydrogen demand",
        inputs={
            b_h2: solph.Flow(
                fix=demand_h2_angepasst,
                nominal_value=1,
                # variable_costs=c_h2_virtual
            )
        }
    )

    # sink for byproduct heat
    sink_heat = solph.components.Sink(
        "heat export",
        inputs={
            b_heat: solph.Flow(
                variable_costs=c_heat
            )
        }
    )

    # sink for byproduct oxygen
    sink_o2 = solph.components.Sink(
        "oxygen export",
        inputs={
            b_o2: solph.Flow(
                variable_costs=c_oxygen
            )
        }
    )

    sink_h2o = solph.components.Sink(
        "water export",
        inputs={
            b_h2o: solph.Flow(
            )
        }
    )

    sink_h2_neg_affr_virt = solph.components.Sink(
        "neg affr h2 sink virt",
        inputs={
            b_h2_neg_affr_virt: solph.Flow(
                variable_costs=-lp_neg_affr_angepasst  # price for keeping neg. balancing energy available
            )
        }
    )

    sink_h2_pos_affr_virt = solph.components.Sink(
        "pos affr h2 sink virt",
        inputs={
            b_h2_pos_affr_virt: solph.Flow(
                variable_costs=-lp_pos_affr_angepasst  # price for keeping neg. balancing energy available
            )
        }
    )

    #### Electrolyzer hydrogen market ####
    # firt part electrolyzer to cover hydrogen demand/production
    electrolyzer1_1 = solph.components.OffsetConverter(
        label='electrolyzer market 1',
        inputs={
            b_el: solph.Flow(
                nominal_value=P_in_max,
                nonconvex=solph.NonConvex(),
                min=P_in_min / P_in_max,
            )
        },
        outputs={
            b_heat: solph.Flow(),
            b_h2: solph.Flow()
        },
        conversion_factors={
            b_heat: slope_heat,
            b_h2: slope_h2
        },
        normed_offsets={
            b_heat: offset_heat,
            b_h2: offset_h2
        }
    )

    # firt part electrolyzer to cover hydrogen demand/production
    electrolyzer1_2 = solph.components.OffsetConverter(
        label='electrolyzer market 2',
        inputs={
            b_el: solph.Flow(
                nominal_value=P_in_max_2,
                nonconvex=solph.NonConvex(),
                min=P_in_min_2 / P_in_max_2,
            )
        },
        outputs={
            b_heat: solph.Flow(),
            b_h2: solph.Flow()
        },
        conversion_factors={
            b_heat: slope_heat_2,
            b_h2: slope_h2_2
        },
        normed_offsets={
            b_heat: offset_heat_2,
            b_h2: offset_h2_2
        }
    )

    #### Electrolyzer negative aFRR ####
    # second part electrolyzer to cover holding of neg. balancing energy
    electrolyzer2_1 = solph.components.OffsetConverter(
        label='electrolyzer neg affr holding',
        inputs={
            b_el_neg_affr_virt: solph.Flow(
                nominal_value=P_in_max,
                nonconvex=solph.NonConvex(),
                min=P_in_min / P_in_max,
                # max=1
            )
        },
        outputs={
            b_h2_neg_affr_virt: solph.Flow()
        },
        conversion_factors={
            b_h2_neg_affr_virt: slope_h2,
        },
        normed_offsets={
            b_h2_neg_affr_virt: offset_h2,
        }
    )

    # firt part electrolyzer to cover hydrogen demand/production
    electrolyzer2_2 = solph.components.OffsetConverter(
        label='electrolyzer neg affr holding 2',
        inputs={
            b_el_neg_affr_virt: solph.Flow(
                nominal_value=P_in_max_2,
                nonconvex=solph.NonConvex(),
                min=1 / P_in_max_2,  # die 1 steht für 1MW der mindestens für Regelenergie angeboten werden muss
            )
        },
        outputs={
            b_h2_neg_affr_virt: solph.Flow()
        },
        conversion_factors={
            b_h2_neg_affr_virt: slope_h2_2
        },
        normed_offsets={
            b_h2_neg_affr_virt: offset_h2_2
        }
    )

    #### Electrolyzer positive aFRR ####
    # fourth part electrolyzer to cover pos. balancing energy
    electrolyzer3_1 = solph.components.OffsetConverter(
        label='electrolyzer pos affr holding',
        inputs={
            b_el_pos_affr_virt: solph.Flow(
                nominal_value=P_in_max,
                nonconvex=solph.NonConvex(),
                min=P_in_min / P_in_max,
            )
        },
        outputs={
            b_h2_pos_affr_virt: solph.Flow()
        },
        conversion_factors={
            b_h2_pos_affr_virt: slope_h2,
        },
        normed_offsets={
            b_h2_pos_affr_virt: offset_h2,
        }
    )

    electrolyzer3_2 = solph.components.OffsetConverter(
        label='electrolyzer pos affr holding 2',
        inputs={
            b_el_pos_affr_virt: solph.Flow(
                nominal_value=P_in_max_2,
                nonconvex=solph.NonConvex(),
                min=1 / P_in_max_2,
            )
        },
        outputs={
            b_h2_pos_affr_virt: solph.Flow()
        },
        conversion_factors={
            b_h2_pos_affr_virt: slope_h2_2
        },
        normed_offsets={
            b_h2_pos_affr_virt: offset_h2_2
        }
    )

    #### Storages ####
    # battery storage
    el_storage = solph.components.GenericStorage(
        label="electricity storage",
        nominal_storage_capacity=el_storage_capacity,
        inputs={
            b_el: solph.Flow(
                nominal_value=el_storage_input_flow,
                variable_costs=el_storage_variable_costs,
                nonconvex=solph.NonConvex()
            )
        },
        outputs={
            b_el: solph.Flow(
                nominal_value=el_storage_output_flow
            )
        },
        loss_rate=el_storage_loss_rate,
        initial_storage_level=el_storage_initial_storage_level,
        balanced=False
        # inflow_conversion_factor=0.9,
        # outflow_conversion_factor=0.9
    )

    # hydrogen storage
    h2_storage = solph.components.GenericStorage(
        label="hydrogen storage",
        nominal_storage_capacity=hydrogen_storage_capacity,
        inputs={
            b_h2: solph.Flow(
                nominal_value=hydrogen_storage_input_flow,
                variable_costs=hydrogen_storage_variable_costs,
                nonconvex=solph.NonConvex()
            )
        },
        outputs={
            b_h2: solph.Flow(
                nominal_value=hydrogen_storage_output_flow
            )
        },
        loss_rate=hydrogen_storage_loss_rate,
        initial_storage_level=hydrogen_storage_initial_storage_level,
        balanced=False
        # inflow_conversion_factor=0.9,
        # outflow_conversion_factor=0.9
    )

    es2.add(b_el, b_h2, b_heat, b_o2, b_h2o, b_el_neg_affr_virt, b_h2_neg_affr_virt, b_el_pos_affr_virt,
            b_h2_pos_affr_virt,
            source_el, source_h2o, source_o2, sink_h2_demand, sink_heat, sink_o2, sink_h2o, source_el_neg_affr_virt,
            sink_h2_neg_affr_virt, source_el_pos_affr_virt, sink_h2_pos_affr_virt,
            electrolyzer1_1, electrolyzer1_2, el_storage, h2_storage, electrolyzer2_1, electrolyzer2_2, electrolyzer3_1,
            electrolyzer3_2
            )

    om = solph.Model(es2)

    myblock = po.Block()
    om.add_component("MyBlock", myblock)

    # es kann nur Ely1_1 oder Ely1_2 produzieren, nicht beide gleichzeitig
    solph.constraints.limit_active_flow_count(
        om, "flow count", [(b_el, electrolyzer1_1), (b_el, electrolyzer1_2)], lower_limit=0, upper_limit=1
    )
    # es kann nur Ely2_1 oder Ely2_2 produzieren, nicht beide gleichzeitig
    solph.constraints.limit_active_flow_count(
        om, "flow count2", [(b_el_neg_affr_virt, electrolyzer2_1), (b_el_neg_affr_virt, electrolyzer2_2)],
        lower_limit=0, upper_limit=1
    )
    # es kann nur Ely3_1 oder Ely3_2 produzieren, nicht beide gleichzeitig
    solph.constraints.limit_active_flow_count(
        om, "flow count3", [(b_el_pos_affr_virt, electrolyzer3_1), (b_el_pos_affr_virt, electrolyzer3_2)],
        lower_limit=0, upper_limit=1
    )


    def water_flow(m, t):
        expr = om.flow[source_h2o, b_h2o, t] == 162 * (
                    om.flow[b_el, electrolyzer1_1, t] + om.flow[b_el, electrolyzer1_2, t])
        return expr


    myblock.water_flow = po.Constraint(om.TIMESTEPS, rule=water_flow)

    def oxygen_flow(m,t):
        expr = om.flow[b_o2, sink_o2, t] == 240 * (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t])
        return expr

    myblock.oxygen_flow = po.Constraint(om.TIMESTEPS, rule=oxygen_flow)


    # Die Produktion von Ely1_1, Ely1_2 und Ely2_1 muss kleiner/gleich der Nennleistung sein
    def limit_active_flow_count_rule_neg(m, t):
        expr = (om.flow[b_el, electrolyzer1_1, t] + om.flow[b_el, electrolyzer1_2, t] + om.flow[
            b_el_neg_affr_virt, electrolyzer2_1, t] + om.flow[b_el_neg_affr_virt, electrolyzer2_2, t] <= P_in_max)
        return expr


    myblock.limit_active_flow_count_neg = po.Constraint(om.TIMESTEPS, rule=limit_active_flow_count_rule_neg)


    # Es muss mindestens so viel Kapazität in Nutzung sein, wei pos. Regelenergie angeboten wird
    def limit_active_flow_count_rule_pos(m, t):
        expr = om.flow[b_el, electrolyzer1_1, t] + om.flow[b_el, electrolyzer1_2, t] >= om.flow[
            b_el_pos_affr_virt, electrolyzer3_1, t] + om.flow[b_el_pos_affr_virt, electrolyzer3_2, t]
        return expr


    myblock.limit_active_flow_count_pos = po.Constraint(om.TIMESTEPS, rule=limit_active_flow_count_rule_pos)

    # Erstellen eines "help time index", über den eine weiterer TimeIndex erstellt wird, in dem alle zeitpunkte enthalten sind, in denen die vorgehaltene Regelenergiemenge bestimmt wird
    help_datetime_index = solph.create_time_index(year=2019, number=8761)  # num_tsteps
    # DateTimeIndex with start times of the control energy time slices
    decision_times = pd.date_range(help_datetime_index[0], help_datetime_index[-1], freq='4h')


    # Sicherstellen, dass für alle Perioden eines Regelenergiezeitlots gengu Speicherkapazität vorhanden ist, falls neg. Regelenergie abgerufen wird

    def min_storage_capa(m, t):
        if datetime_index[t] in decision_times:
            expr = (hydrogen_storage_capacity - om.GenericStorageBlock.storage_content[h2_storage, t] >=
                    om.flow[electrolyzer2_1, b_h2_neg_affr_virt, t] + om.flow[electrolyzer2_2, b_h2_neg_affr_virt, t] +
                    om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] -
                    demand_h2_angepasst[t])
            return expr
        else:
            return po.Constraint.Skip


    myblock.min_storage_capa = po.Constraint(om.TIMESTEPS, rule=min_storage_capa)


    def min_storage_capa1(m, t):
        if datetime_index[t] in decision_times:
            if t + 1 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (hydrogen_storage_capacity - om.GenericStorageBlock.storage_content[h2_storage, t] >=
                        om.flow[electrolyzer2_1, b_h2_neg_affr_virt, t] * 2 + om.flow[
                            electrolyzer2_2, b_h2_neg_affr_virt, t] * 2 +
                        om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] -
                        demand_h2_angepasst[t] - demand_h2_angepasst[t + 1])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.min_storage_capa1 = po.Constraint(om.TIMESTEPS, rule=min_storage_capa1)


    def min_storage_capa2(m, t):
        if datetime_index[t] in decision_times:
            if t + 2 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (hydrogen_storage_capacity - om.GenericStorageBlock.storage_content[h2_storage, t] >=
                        om.flow[electrolyzer2_1, b_h2_neg_affr_virt, t] * 3 + om.flow[
                            electrolyzer2_2, b_h2_neg_affr_virt, t] * 3 +
                        om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] +
                        om.flow[electrolyzer1_1, b_h2, t + 2] + om.flow[electrolyzer1_2, b_h2, t + 2] -
                        demand_h2_angepasst[t] - demand_h2_angepasst[t + 1] - demand_h2_angepasst[t + 2])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.min_storage_capa2 = po.Constraint(om.TIMESTEPS, rule=min_storage_capa2)


    def min_storage_capa3(m, t):
        if datetime_index[t] in decision_times:
            if t + 3 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (hydrogen_storage_capacity - om.GenericStorageBlock.storage_content[h2_storage, t] >=
                        om.flow[electrolyzer2_1, b_h2_neg_affr_virt, t] * 4 + om.flow[
                            electrolyzer2_2, b_h2_neg_affr_virt, t] * 4 +
                        om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] +
                        om.flow[electrolyzer1_1, b_h2, t + 2] + om.flow[electrolyzer1_2, b_h2, t + 2] +
                        om.flow[electrolyzer1_1, b_h2, t + 3] + om.flow[electrolyzer1_2, b_h2, t + 3] -
                        demand_h2_angepasst[t] - demand_h2_angepasst[t + 1] - demand_h2_angepasst[t + 2] -
                        demand_h2_angepasst[t + 3])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.min_storage_capa3 = po.Constraint(om.TIMESTEPS, rule=min_storage_capa3)


    def min_storage_capa_safety(m, t):
        if datetime_index[t] in decision_times:
            if hydrogen_storage_capacity - hydrogen_storage_initial_storage_level * hydrogen_storage_capacity <= 40:
                expr = (om.flow[electrolyzer2_1, b_h2_neg_affr_virt, t] + om.flow[
                    electrolyzer2_2, b_h2_neg_affr_virt, t]) == 0  # (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t]) *
                return expr
            else:
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.min_storage_capa_safety = po.Constraint(om.TIMESTEPS, rule=min_storage_capa_safety)


    def min_storage_pos_safety(m, t):
        if datetime_index[t] in decision_times:
            if hydrogen_storage_initial_storage_level * hydrogen_storage_capacity <= 40:
                expr = om.flow[electrolyzer3_1, b_h2_pos_affr_virt, t] + om.flow[
                    electrolyzer3_2, b_h2_pos_affr_virt, t] == 0
                return expr
            else:
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.min_storage_pos_safety = po.Constraint(om.TIMESTEPS, rule=min_storage_pos_safety)


    # Die Produktion von Ely1_1/Ely1_2 plus den Speicherfüllstand abzüglich der pos. Regelenergie muss mindestens so groß sein, wie die Nachfrage
    # damit soll sichergestellt werden, dass die Nachfrage gedeckt ist auch wenn pos. Regelenergie abgerufen wird
    def production_constraint_pos_affr(m, t):
        expr = (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] -
                (om.flow[electrolyzer3_1, b_h2_pos_affr_virt, t] + om.flow[electrolyzer3_2, b_h2_pos_affr_virt, t]) +
                om.GenericStorageBlock.storage_content[h2_storage, t] * (1 - hydrogen_storage_loss_rate) >=
                demand_h2_angepasst[t])  #
        return expr


    myblock.production_constraint_pos_affr = po.Constraint(om.TIMESTEPS, rule=production_constraint_pos_affr)


    def production_constraint_pos_affr1(m, t):
        if datetime_index[t] in decision_times:
            if t + 1 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] +
                        om.GenericStorageBlock.storage_content[h2_storage, t] * (1 - hydrogen_storage_loss_rate) -
                        (om.flow[electrolyzer3_1, b_h2_pos_affr_virt, t] + om.flow[
                            electrolyzer3_2, b_h2_pos_affr_virt, t]) * 2 >=
                        demand_h2_angepasst[t] + demand_h2_angepasst[t + 1])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.production_constraint_pos_affr1 = po.Constraint(om.TIMESTEPS, rule=production_constraint_pos_affr1)


    def production_constraint_pos_affr2(m, t):
        if datetime_index[t] in decision_times:
            if t + 2 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] +
                        om.flow[electrolyzer1_1, b_h2, t + 2] + om.flow[electrolyzer1_2, b_h2, t + 2] +
                        om.GenericStorageBlock.storage_content[h2_storage, t] * (1 - hydrogen_storage_loss_rate) ** 2 -
                        (om.flow[electrolyzer3_1, b_h2_pos_affr_virt, t] + om.flow[
                            electrolyzer3_2, b_h2_pos_affr_virt, t]) * 3 >=
                        demand_h2_angepasst[t] + demand_h2_angepasst[t + 1] + demand_h2_angepasst[t + 2])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.production_constraint_pos_affr2 = po.Constraint(om.TIMESTEPS, rule=production_constraint_pos_affr2)


    def production_constraint_pos_affr3(m, t):
        if datetime_index[t] in decision_times:
            if t + 3 < len(om.TIMESTEPS):  # Sicherstellen, dass t+1 im Bereich ist
                expr = (om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t] +
                        om.flow[electrolyzer1_1, b_h2, t + 1] + om.flow[electrolyzer1_2, b_h2, t + 1] +
                        om.flow[electrolyzer1_1, b_h2, t + 2] + om.flow[electrolyzer1_2, b_h2, t + 2] +
                        om.flow[electrolyzer1_1, b_h2, t + 3] + om.flow[electrolyzer1_2, b_h2, t + 3] +
                        om.GenericStorageBlock.storage_content[h2_storage, t] * (1 - hydrogen_storage_loss_rate) ** 3 -
                        (om.flow[electrolyzer3_1, b_h2_pos_affr_virt, t] + om.flow[
                            electrolyzer3_2, b_h2_pos_affr_virt, t]) * 4 >=
                        demand_h2_angepasst[t] + demand_h2_angepasst[t + 1] + demand_h2_angepasst[t + 2] +
                        demand_h2_angepasst[t + 3])
                return expr
            else:
                # Falls t+1 außerhalb des Bereichs liegt, Constraint für diesen Fall auslassen
                return po.Constraint.Skip
        else:
            return po.Constraint.Skip


    myblock.production_constraint_pos_affr3 = po.Constraint(om.TIMESTEPS, rule=production_constraint_pos_affr3)


    # Time Constraint - so the amount of balacing energy can only change at 0,4,8,12,16,20

    # Immer zu Beginn eines 4h-Slots kann die angebotene Regelenergiemenge geändert werden, die restlichen 3h muss der selbe Wert angeboten werden
    def time_constraint_neg_affr(m, t):
        if datetime_index[t] not in decision_times:
            if t == 0:
                expr = om.flow[source_el_neg_affr_virt, b_el_neg_affr_virt, t] == electricity_flow_ely2_1
                return expr
            else:
                expr = om.flow[source_el_neg_affr_virt, b_el_neg_affr_virt, t] == om.flow[
                    source_el_neg_affr_virt, b_el_neg_affr_virt, t - 1]
                return expr
        else:
            return po.Constraint.Skip


    myblock.time_constraint_neg_affr = po.Constraint(om.TIMESTEPS, rule=time_constraint_neg_affr)


    def time_constraint_pos_affr(m, t):
        if datetime_index[t] not in decision_times:
            if t == 0:
                expr = om.flow[source_el_pos_affr_virt, b_el_pos_affr_virt, t] == electricity_flow_ely3_1
                return expr
            else:
                expr = om.flow[source_el_pos_affr_virt, b_el_pos_affr_virt, t] == om.flow[
                    source_el_pos_affr_virt, b_el_pos_affr_virt, t - 1]
                return expr
        else:
            return po.Constraint.Skip


    myblock.time_constraint_pos_affr = po.Constraint(om.TIMESTEPS, rule=time_constraint_pos_affr)

    # lösen des Optimierungsproblems
    om.solve("gurobi")

    results = solph.views.convert_keys_to_strings(om.results(), keep_none_type=True)

    # Werte, die nach der ersten Optimierung an die zweite Optimierung (Auswertung) übergeben werden
    electricity_flow_ely1_1 = results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].iloc[0]
    electricity_flow_ely1_2 = results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].iloc[0]
    electricity_flow_ely2_1 = \
    results[("neg affr virt electricity bus", "electrolyzer neg affr holding")]["sequences"]["flow"].iloc[0]
    electricity_flow_ely2_2 = \
    results[("neg affr virt electricity bus", "electrolyzer neg affr holding 2")]["sequences"]["flow"].iloc[0]
    electricity_flow_ely3_1 = \
    results[("pos affr virt electricity bus", "electrolyzer pos affr holding")]["sequences"]["flow"].iloc[0]
    electricity_flow_ely3_2 = \
    results[("pos affr virt electricity bus", "electrolyzer pos affr holding 2")]["sequences"]["flow"].iloc[0]

    storage_content_el_storage = results[("electricity storage", None)]["sequences"]["storage_content"].iloc[
                                     0] / el_storage_capacity
    storage_content_h2_storage = results[("hydrogen storage", None)]["sequences"]["storage_content"].iloc[
                                     0] / hydrogen_storage_capacity

    print(n)

    # definition of time index
    datetime_index = solph.create_time_index(year=2019, number=1, start=start_time)

    es3 = solph.EnergySystem(timeindex=datetime_index, infer_last_interval=False)

    # Definition Bus-Components
    b_el = solph.Bus("electricity bus")
    b_h2 = solph.Bus("hydrogen bus")
    b_heat = solph.Bus("heat bus")
    b_o2 = solph.Bus("oxygen bus")
    b_h2o = solph.Bus("water bus")

    ##### Definition der Komponenten #####

    # electricity source for basic hydrogen demand
    source_el = solph.components.Source(
        "electricity import",
        outputs={
            b_el: solph.Flow(
                variable_costs=c_el_angepasst
            )
        }
    )

    source_h2o = solph.components.Source(
        "water import",
        outputs={
            b_h2o: solph.Flow(
                variable_costs=0.0015  # €/l Wasser
            )
        }
    )

    source_o2 = solph.components.Source(
        "oxygen import",
        outputs={
            b_o2: solph.Flow(
            )
        }
    )

    # Sink for fix haydrogen demand via contract
    sink_h2_demand = solph.components.Sink(
        "hydrogen demand",
        inputs={
            b_h2: solph.Flow(
                fix=demand_h2_angepasst,
                nominal_value=1,
                # variable_costs=c_h2_virtual
            )
        }
    )

    # sink for byproduct heat
    sink_heat = solph.components.Sink(
        "heat export",
        inputs={
            b_heat: solph.Flow(
                variable_costs=c_heat
            )
        }
    )

    # sink for byproduct oxygen
    sink_o2 = solph.components.Sink(
        "oxygen export",
        inputs={
            b_o2: solph.Flow(
                variable_costs=c_oxygen
            )
        }
    )

    sink_h2o = solph.components.Sink(
        "water export",
        inputs={
            b_h2o: solph.Flow(
            )
        }
    )

    #### Electrolyzer hydrogen market ####
    # firt part electrolyzer to cover hydrogen demand/production
    electrolyzer1_1 = solph.components.OffsetConverter(
        label='electrolyzer market 1',
        inputs={
            b_el: solph.Flow(
                nominal_value=P_in_max,
                nonconvex=solph.NonConvex(),
                min=P_in_min / P_in_max,  #
            )
        },
        outputs={
            b_heat: solph.Flow(),
            b_h2: solph.Flow()
        },
        conversion_factors={
            b_heat: slope_heat,
            b_h2: slope_h2
        },
        normed_offsets={
            b_heat: offset_heat,
            b_h2: offset_h2
        }
    )

    # firt part electrolyzer to cover hydrogen demand/production
    electrolyzer1_2 = solph.components.OffsetConverter(
        label='electrolyzer market 2',
        inputs={
            b_el: solph.Flow(
                nominal_value=P_in_max_2,
                nonconvex=solph.NonConvex(),
                min=P_in_min_2 / P_in_max_2,
            )
        },
        outputs={
            b_heat: solph.Flow(),
            b_h2: solph.Flow()
        },
        conversion_factors={
            b_heat: slope_heat_2,
            b_h2: slope_h2_2
        },
        normed_offsets={
            b_heat: offset_heat_2,
            b_h2: offset_h2_2
        }
    )

    #### Storages ####
    # battery storage
    el_storage = solph.components.GenericStorage(
        label="electricity storage",
        nominal_storage_capacity=el_storage_capacity,
        inputs={
            b_el: solph.Flow(
                nominal_value=el_storage_input_flow,
                variable_costs=el_storage_variable_costs,
                nonconvex=solph.NonConvex()
            )
        },
        outputs={
            b_el: solph.Flow(
                nominal_value=el_storage_output_flow
            )
        },
        loss_rate=el_storage_loss_rate,
        initial_storage_level=storage_content_el_storage,
        balanced=False
        # inflow_conversion_factor=0.9,
        # outflow_conversion_factor=0.9
    )

    # hydrogen storage
    h2_storage = solph.components.GenericStorage(
        label="hydrogen storage",
        nominal_storage_capacity=hydrogen_storage_capacity,
        inputs={
            b_h2: solph.Flow(
                nominal_value=hydrogen_storage_input_flow,
                variable_costs=hydrogen_storage_variable_costs,
                nonconvex=solph.NonConvex()
            )
        },
        outputs={
            b_h2: solph.Flow(
                nominal_value=hydrogen_storage_output_flow
            )
        },
        loss_rate=hydrogen_storage_loss_rate,
        initial_storage_level=storage_content_h2_storage,
        balanced=False
        # inflow_conversion_factor=0.9,
        # outflow_conversion_factor=0.9
    )

    es3.add(b_el, b_h2, b_heat, b_o2, b_h2o,
            source_el, source_h2o, source_o2, sink_h2_demand, sink_heat, sink_o2, sink_h2o,
            electrolyzer1_1, electrolyzer1_2, el_storage, h2_storage
            )

    om3 = solph.Model(es3)

    myblock3 = po.Block()
    om3.add_component("MyBlock3", myblock3)


    def water_flow(m, t):
        expr = om3.flow[source_h2o, b_h2o, t] == 162 * (
                    om3.flow[b_el, electrolyzer1_1, t] + om3.flow[b_el, electrolyzer1_2, t])
        return expr


    myblock3.water_flow = po.Constraint(om3.TIMESTEPS, rule=water_flow)

    def oxygen_flow(m,t):
        expr = om3.flow[b_o2, sink_o2, t] == 240 * (om3.flow[electrolyzer1_1, b_h2, t] + om3.flow[electrolyzer1_2, b_h2, t])
        return expr

    myblock3.oxygen_flow = po.Constraint(om3.TIMESTEPS, rule=oxygen_flow)



    def flow_ely1_1(m, t):
        if b_neg[n] > 0:
            if electricity_flow_ely1_1 + electricity_flow_ely1_2 + b_neg[n] * (
                    electricity_flow_ely2_1 + electricity_flow_ely2_2) > 2:
                expr = om3.flow[b_el, electrolyzer1_1, t] == electricity_flow_ely1_1 + b_neg[n] * (
                            electricity_flow_ely2_1 + electricity_flow_ely2_2)
                return expr
            else:
                expr = om3.flow[b_el, electrolyzer1_1, t] == electricity_flow_ely1_1
                return expr
        elif b_pos[n] > 0:
            if electricity_flow_ely1_1 > 0:
                if electricity_flow_ely1_1 - electricity_flow_ely3_1 - electricity_flow_ely3_2 <= 2:
                    expr = om3.flow[b_el, electrolyzer1_1, t] == 0
                    return expr
                else:
                    expr = om3.flow[b_el, electrolyzer1_1, t] == electricity_flow_ely1_1 - b_pos[n] * (
                                electricity_flow_ely3_1 + electricity_flow_ely3_2)
                    return expr
            else:
                expr = om3.flow[b_el, electrolyzer1_1, t] == electricity_flow_ely1_1
                return expr
        else:
            expr = om3.flow[b_el, electrolyzer1_1, t] == electricity_flow_ely1_1
            return expr


    myblock3.flow_ely1_1 = po.Constraint(om3.TIMESTEPS, rule=flow_ely1_1)


    def flow_ely1_2(m, t):
        if b_neg[n] > 0:
            if electricity_flow_ely1_1 + electricity_flow_ely1_2 + b_neg[n] * (
                    electricity_flow_ely2_1 + electricity_flow_ely2_2) <= 2:
                expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_2 + b_neg[n] * (
                            electricity_flow_ely2_1 + electricity_flow_ely2_2)
                return expr
            else:
                expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_2
                return expr
        elif b_pos[n] > 0:
            if electricity_flow_ely1_1 > 0:
                if electricity_flow_ely1_1 - electricity_flow_ely3_1 - electricity_flow_ely3_2 <= 2:
                    expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_1 - b_pos[n] * (
                                electricity_flow_ely3_1 + electricity_flow_ely3_2)
                    return expr
                else:
                    expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_2
                    return expr
            else:
                expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_2 - b_pos[n] * (
                            electricity_flow_ely3_1 + - electricity_flow_ely3_2)
                return expr
        else:
            expr = om3.flow[b_el, electrolyzer1_2, t] == electricity_flow_ely1_2
            return expr


    myblock3.flow_ely1_2 = po.Constraint(om3.TIMESTEPS, rule=flow_ely1_2)

    # lösen des Optimierungsproblems
    om3.solve("gurobi")

    results3 = solph.views.convert_keys_to_strings(om3.results(), keep_none_type=True)

    # Füllstände der Speicher, die in erste Optimierung wieder übergeben werden
    el_storage_initial_storage_level = results3[("electricity storage", None)]["sequences"]["storage_content"].iloc[
                                           1] / el_storage_capacity
    hydrogen_storage_initial_storage_level = results3[("hydrogen storage", None)]["sequences"]["storage_content"].iloc[
                                                 1] / hydrogen_storage_capacity

    # Sammeln aller Informationen für DataFrame
    time.append(start_time.strftime("%d-%m-%Y %H:%M:%S"))
    # start_time += dt.timedelta(hours=1)

    opt1_input_ely_1_1.append(electricity_flow_ely1_1)
    input_ely_1_1.append(results3[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].iloc[0])
    output_ely_1_1.append(results3[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"].iloc[0])

    opt1_input_ely_1_2.append(electricity_flow_ely1_2)
    input_ely_1_2.append(results3[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].iloc[0])
    output_ely_1_2.append(results3[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"].iloc[0])

    nachfrage.append(demand_h2_angepasst[0])

    vorhalten_neg_affr.append(electricity_flow_ely2_1 + electricity_flow_ely2_2)
    abrufen_neg_affr.append(b_neg[n] * (electricity_flow_ely2_1 + electricity_flow_ely2_2))
    neg_signal.append(b_neg[n])

    vorhalten_pos_affr.append(electricity_flow_ely3_1 + electricity_flow_ely3_2)
    abrufen_pos_affr.append(b_pos[n] * (electricity_flow_ely3_1 + electricity_flow_ely3_2))
    pos_signal.append(b_pos[n])

    storage_content_h2.append(results3[("hydrogen storage", None)]["sequences"]["storage_content"].iloc[0])
    input2_h2_storage.append(results3[("hydrogen bus", "hydrogen storage")]["sequences"]["flow"].iloc[0])
    output2_h2_storage.append(results3[("hydrogen storage", "hydrogen bus")]["sequences"]["flow"].iloc[0])

    storage_content_el.append(results3[("electricity storage", None)]["sequences"]["storage_content"].iloc[0])
    input2_el_storage.append(results3[("electricity bus", "electricity storage")]["sequences"]["flow"].iloc[0])
    output2_el_storage.append(results3[("electricity storage", "electricity bus")]["sequences"]["flow"].iloc[0])

    strombezug.append(results3[("electricity import", "electricity bus")]["sequences"]["flow"].iloc[0])
    menge_abwärme.append(results3[("heat bus", "heat export")]["sequences"]["flow"].iloc[0])
    menge_sauerstoff.append(results3[("oxygen bus", "oxygen export")]["sequences"]["flow"].iloc[0])
    menge_wasser.append(results3[("water import", "water bus")]["sequences"]["flow"].iloc[0])

    print(n)


df4 = pd.DataFrame()
df4['Zeit'] = time[:]
df4['Input Ely1 ohne affr'] = opt1_input_ely_1_1
df4['Input Flow Ely 1 [MWh]'] = input_ely_1_1
df4['Output Flow Ely 1 [MWh]'] = output_ely_1_1
df4['Input Ely1_2 ohne affr'] = opt1_input_ely_1_2
df4['Input Flow Ely 1_2 [MWh]'] = input_ely_1_2
df4['Output Flow Ely 1_2 [MWh]'] = output_ely_1_2

df4['feste H2-Nachfrage'] = nachfrage

df4['neg. aFFR vorgehalten'] = vorhalten_neg_affr
df4['neg. aFFR abgerufen'] = abrufen_neg_affr
df4['b_neg'] = neg_signal

df4['pos. aFFR vorgehalten'] = vorhalten_pos_affr
df4['pos. aFFR abgerufen'] = abrufen_pos_affr
df4['b_pos'] = pos_signal

df4['hydrogen storage content'] = storage_content_h2
df4['Input Flow 2 Hydrogen Storage'] = input2_h2_storage
df4['Output Flow 2 Hydrogen Storage'] = output2_h2_storage

df4['electricity storage content'] = storage_content_el
df4['Input Flow 2 Electricity Storage'] = input2_el_storage
df4['Output Flow 2 Electricity Storage'] = output2_el_storage
df4['Strombezug'] = strombezug
df4['Menge Abwärme'] = menge_abwärme
df4['Menge Sauerstoff'] =menge_sauerstoff
df4['Menge Wasser'] = menge_wasser

print(df4)