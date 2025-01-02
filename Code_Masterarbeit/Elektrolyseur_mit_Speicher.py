from oemof import solph
import pandas as pd
import numpy as np
import pyomo.environ as po
import random
import datetime as dt

##################### einzugebende Parameter #####################
num_tsteps = 8760  # Anzahl der Zeitschritte
c_h2 = 0  # angenommener H2-Preis für freien H2-Markt €/MWh
c_heat = 0
c_oxygen = 0

power_ely = 20  # Beispiel-Leistung des Elektrolyseurs in MW
investment_cost_ely = 1000  # Beispiel-Investitionskosten in Euro/kW
number_years = 20  # Abschreibungsdauer in Jahren
interest_rate = 0.06  # Zinssatz für die Abschreibung
w = 0.04  # Kosten für Wartung, Betrieb, Versicherung

power_h2_storage = 150  # MWh
investment_cost_h2_storage = 30  # €/kWh
power_el_storage = 5  # MWh
investment_cost_el_storage = 300  # 300 #€/kWh

investment_cost_total = (
                                    investment_cost_ely * power_ely + investment_cost_h2_storage * power_h2_storage + investment_cost_el_storage * power_el_storage) * 1000

# annualized capex
a = (((1 + interest_rate) ** number_years) * interest_rate) / (((1 + interest_rate) ** number_years) - 1)
annualized_cost = investment_cost_total * (a + w)

# Daten Teillastverahlten
eta_h2_min = 0.60  # efficiency at P_in_min
eta_h2_max = 0.50  # efficiency at P_in_max
P_in_min = 2
P_in_max = 20

# slope und offset for part-load behavior hydrogen, heat
slope_h2, offset_h2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min,
                                                                                           eta_at_max=0.5,
                                                                                           eta_at_min=0.6)

slope_heat, offset_heat = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min,
                                                                                               eta_at_max=0.5,
                                                                                               eta_at_min=0.4)

# Daten Teillastverahlten
eta_h2_min_2 = 0  # efficiency at P_in_min
eta_h2_max_2 = 0.60  # efficiency at P_in_max
P_in_min_2 = 0
P_in_max_2 = 2

# slope und offset for part-load behavior hydrogen, heat, oxygen
slope_h2_2, offset_h2_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2,
                                                                                               eta_at_max=eta_h2_max_2,
                                                                                               eta_at_min=eta_h2_min_2)

slope_heat_2, offset_heat_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2,
                                                                                                   P_in_min_2,
                                                                                                   eta_at_max=0.4,
                                                                                                   eta_at_min=1)

##################### einlesen von Zeitreihen #####################

# Strompreisdaten
konzessionsabgabe = 1.1  # €/MWh
umlage_strom_nev = 4  # €/MWh
umsatzsteuer = 0.19  # in %
ppa = 50  # €/MWh
c_el = pd.read_excel(
    "/Users/lucajahner/Documents/Masterarbeit/Modell/Daten/DayAhead_Boersenstrompreis_stuendlich_2019_energy_charts.xlsx")  # DayAhead_Börsenstrompreise_stündlich_2023_energy_charts.xlsx
c_el = c_el["Preis (EUR/MWh)"]  # Preis für Beschaffung und Betrieb
c_el = (c_el + konzessionsabgabe + umlage_strom_nev) * (1 + umsatzsteuer)  # Strompreis inkl. Umlagen und Abgaben
# c_el = (ppa + konzessionsabgabe + umlage_strom_nev) * (1+umsatzsteuer)
# c_el = [c_el]*8760

random.seed(42)
demand_h2 = [random.randint(0, 10) for _ in range(8760)]

# Daten Speicher
el_storage_capacity = 5
el_storage_input_flow = 5
el_storage_output_flow = 5
el_storage_loss_rate = 0.002  # loss rate per hour
el_storage_variable_costs = 0
el_storage_initial_storage_level = 0
hydrogen_storage_capacity = 150
hydrogen_storage_input_flow = 150
hydrogen_storage_output_flow = 150
hydrogen_storage_variable_costs = 0
hydrogen_storage_loss_rate = 0.002
hydrogen_storage_initial_storage_level = 0


def find_min_lcoh2(c_h2_virtual):
    start_time = dt.datetime(2019, 1, 1, 0, 0, 0)  # festlegen von Startzeitpunkt
    datetime_index = solph.create_time_index(number=num_tsteps, start=start_time)

    es2 = solph.EnergySystem(timeindex=datetime_index, infer_last_interval=False)

    # Definition Bus-Components
    b_el = solph.Bus("electricity bus")
    b_h2 = solph.Bus("hydrogen bus")
    b_heat = solph.Bus("heat bus")
    b_o2 = solph.Bus("oxygen bus")
    b_h2o = solph.Bus("water bus")

    # electricity source for basic hydrogen demand
    source_el = solph.components.Source(
        "electricity import",
        outputs={
            b_el: solph.Flow(
                variable_costs=c_el
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
                # fix=demand_h2,
                # nominal_value=1,
                variable_costs=-c_h2_virtual
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

    es2.add(b_el, b_h2, b_heat, b_o2, b_h2o,
            source_el, source_h2o, source_o2, sink_h2_demand, sink_heat, sink_o2, sink_h2o,
            electrolyzer1_1, electrolyzer1_2, el_storage, h2_storage  #
            )

    om = solph.Model(es2)

    myblock = po.Block()
    om.add_component("MyBlock", myblock)

    # es kann nur Ely1_1 oder Ely1_2 produzieren, nicht beide gleichzeitig
    solph.constraints.limit_active_flow_count(
        om, "flow count", [(b_el, electrolyzer1_1), (b_el, electrolyzer1_2)], lower_limit=0, upper_limit=1
    )

    def water_flow(m, t):
        expr = om.flow[source_h2o, b_h2o, t] == 162 * om.flow[source_el, b_el, t]
        return expr

    myblock.water_flow = po.Constraint(om.TIMESTEPS, rule=water_flow)

    def oxygen_flow(m, t):
        expr = om.flow[b_o2, sink_o2, t] == 240 * (
                    om.flow[electrolyzer1_1, b_h2, t] + om.flow[electrolyzer1_2, b_h2, t])
        return expr

    myblock.oxygen_flow = po.Constraint(om.TIMESTEPS, rule=oxygen_flow)

    # lösen des Optimierungsproblems
    om.solve("gurobi")

    results = solph.views.convert_keys_to_strings(om.results(), keep_none_type=True)

    c_el_neu = list(c_el.copy())
    c_el_neu.append(np.nan)
    demand_h2_neu = list(demand_h2.copy())
    demand_h2_neu.append(np.nan)

    df = pd.DataFrame()
    df['Input Flow Ely 1_1 [MWh]'] = results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"]
    df['Input Flow Ely 1_2 [MWh]'] = results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"]
    df['Output Flow Ely 1_1 [MWh]'] = results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"]
    df['Output Flow Ely 1_2 [MWh]'] = results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"]
    df['Efficiency Ely'] = (
            (results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"] +
             results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"]) /
            (results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"] +
             results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"]))

    df['Strompreis [€/MWh]'] = c_el_neu
    df['feste H2-Nachfrage'] = demand_h2_neu
    df['Input El Storage'] = results[("electricity storage", None)]["sequences"]["storage_content"]
    df['Input H2 Storage'] = results[("hydrogen storage", None)]["sequences"]["storage_content"]
    df['Input Flow El Storage'] = results[("electricity bus", "electricity storage")]["sequences"]["flow"]
    df['Input Flow H2 Storage'] = results[("hydrogen bus", "hydrogen storage")]["sequences"]["flow"]

    arr = results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1] + \
          results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[:-1]
    betriebsstunden = sum(np.array(arr) > 0)
    betrieb_bei_volllast = sum(np.array(arr) == power_ely)

    volllaststunden_el = ((sum(results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1]) +
                           sum(results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[
                               :-1])) /
                          power_ely)

    menge_abwärme = sum(results[("electrolyzer market 1", "heat bus")]["sequences"]["flow"].values[:-1] +
                        results[("electrolyzer market 2", "heat bus")]["sequences"]["flow"].values[:-1])
    menge_sauerstoff = sum(results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"].values[:-1] +
                           results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"].values[:-1]) * 240
    einnahmen_abwärme = sum(results[("electrolyzer market 1", "heat bus")]["sequences"]["flow"].values[:-1] +
                            results[("electrolyzer market 2", "heat bus")]["sequences"]["flow"].values[:-1]) * c_heat
    einnahmen_sauerstoff = sum(results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"].values[:-1] +
                               results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"].values[
                               :-1]) * 240 * c_oxygen

    # totale variable Kosten werden berechnet, indem die bezogene Strommenge mit den Strompreisen multipliziert werden
    cost_el_ely1 = sum(results[("electricity import", "electricity bus")]["sequences"]["flow"].values[:-1] * c_el)
    '''
    (sum((results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1] + 
                         results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[:-1] + 
                         results[("electricity bus", "electricity storage")]["sequences"]["flow"].values[:-1] - 
                         results[("electricity storage", "electricity bus")]["sequences"]["flow"].values[:-1]) * c_el)) 
    '''
    cost_water = sum(results[("water import", "water bus")]["sequences"]["flow"].values[:-1]) * 0.0015
    # annualisierte Investitionskosten werden zu den variablen Kosten addiert um die gesamten Kosten zu betrachten
    total_cost_el = cost_el_ely1 + annualized_cost + cost_water - einnahmen_abwärme - einnahmen_sauerstoff
    # Berechnung der produzierten Wasserstoffmenge
    produced_h2 = sum(results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"].values[:-1] +
                      results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"].values[:-1])
    # produced_h2 = (results[("electrolyzer market 1", "hydrogen bus")]["sequences"]["flow"] +
    #    results[("electrolyzer market 2", "hydrogen bus")]["sequences"]["flow"])
    # produced_h2 = sum(produced_h2) #results[("hydrogen bus", "hydrogen demand")]["sequences"]["flow"].values[:-1]
    test = sum(results[("hydrogen bus", "hydrogen demand")]["sequences"]["flow"].values[:-1])

    # Gestehungskosten werden berechnet, indem die Gesamtkosten durch die Summe der produzierten Menge dividiert wird
    if produced_h2 == 0:
        lcoh2 = total_cost_el
    else:
        lcoh2 = total_cost_el / produced_h2

    df2 = pd.DataFrame()
    df2['LCOH2 [€/MWh]'] = [lcoh2]
    df2['LCOH2 [€/kg]'] = [(lcoh2 * 33.33) / 1000]
    df2['Betriebsstunden'] = [betriebsstunden]
    df2['Betrieb bei Volllast'] = [betrieb_bei_volllast]
    df2['Volllaststunden (elektrisch)'] = [volllaststunden_el]
    df2['jährliche Investitionskosten [€]'] = [annualized_cost]
    df2['Stromkosten [€]'] = [cost_el_ely1]
    df2['Wasserkosten [€]'] = [cost_water]
    df2['Gesamtkosten [€]'] = [total_cost_el]
    df2['produzierte Menge Wasserstoff [MWh]'] = [produced_h2]
    df2['Menge Abwärme [MWh]'] = [menge_abwärme]
    df2['Menge Sauerstoff [t]'] = [menge_sauerstoff]
    df2['Einnahmen Abwärme'] = [einnahmen_abwärme]
    df2['Einnahmen O2'] = [einnahmen_sauerstoff]

    return lcoh2, df, df2, test


# festlegen von sehr hohen Ausgangsgestehungskosten
min_lcoh2 = 10000000

for c_h2_virtual in range(130, 131):
    lcoh2, df, df2, test = find_min_lcoh2(c_h2_virtual)
    print(c_h2_virtual, lcoh2)
    if lcoh2 <= min_lcoh2:
        min_lcoh2 = lcoh2
        c_at_min = c_h2_virtual
        min_df = df
        min_df2 = df2
    else:
        break

min_lcoh2, c_at_min