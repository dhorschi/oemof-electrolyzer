from oemof import solph
import pandas as pd
import numpy as np
import pyomo.environ as po
import random
import datetime as dt

##################### einzugebende Parameter #####################
num_tsteps = 8760 #Anzahl der Zeitschritte
c_h2 = 0 #angenommener H2-Preis für freien H2-Markt €/MWh
c_heat = 0
c_oxygen = 0

power_ely = 20  # Beispiel-Leistung des Elektrolyseurs in MW
investment_cost_ely = 1500  # Beispiel-Investitionskosten in Euro/kW
number_years = 20 #Abschreibungsdauer in Jahren
interest_rate = 0.06 #Zinssatz für die Abschreibung

#annualized capex
a = (((1+interest_rate)**number_years)*interest_rate)/(((1+interest_rate)**number_years)-1)
annualized_cost = investment_cost_ely * power_ely * 1000 * a


#Daten Teillastverahlten
eta_h2_min = 0.60 #efficiency at P_in_min
eta_h2_max = 0.50 #efficiency at P_in_max
P_in_min = 2
P_in_max = 20

#slope und offset for part-load behavior hydrogen, heat, oxygen
slope_h2, offset_h2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min, eta_at_max=0.5, eta_at_min=0.6)

slope_heat, offset_heat = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min, eta_at_max=0.4, eta_at_min=0.3)

slope_o2, offset_o2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max, P_in_min, eta_at_max=0.2, eta_at_min=0.1)

#Daten Teillastverahlten
eta_h2_min_2 = 0 #efficiency at P_in_min
eta_h2_max_2 = 0.60 #efficiency at P_in_max
P_in_min_2 = 0
P_in_max_2 = 2

#slope und offset for part-load behavior hydrogen, heat, oxygen
slope_h2_2, offset_h2_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2, eta_at_max=eta_h2_max_2, eta_at_min=eta_h2_min_2)

slope_heat_2, offset_heat_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2, eta_at_max=0.4, eta_at_min=0)

slope_o2_2, offset_o2_2 = solph.components._offset_converter.slope_offset_from_nonconvex_input(P_in_max_2, P_in_min_2, eta_at_max=0.1, eta_at_min=0)



##################### einlesen von Zeitreihen #####################

#Strompreisdaten
c_el = pd.read_excel("Daten/DayAhead_Boersenstrompreis_stuendlich_2019_energy_charts.xlsx") #DayAhead_Börsenstrompreise_stündlich_2023_energy_charts.xlsx
c_el = c_el["Preis (EUR/MWh)"]#.iloc[:]


random.seed(42)
demand_h2 = [random.randint(0, 10) for _ in range(8760)]


###################### Main Code ######################
def find_min_lcoh2(c_h2_virtual):
    start_time = dt.datetime(2019, 1, 1, 0, 0, 0)  # festlegen von Startzeitpunkt
    datetime_index = solph.create_time_index(number=num_tsteps, start=start_time)

    es2 = solph.EnergySystem(timeindex=datetime_index, infer_last_interval=False)

    # Definition Bus-Components
    b_el = solph.Bus("electricity bus")
    b_h2 = solph.Bus("hydrogen bus")
    b_heat = solph.Bus("heat bus")
    b_o2 = solph.Bus("oxygen bus")

    # electricity source for basic hydrogen demand
    source_el = solph.components.Source(
        "electricity import",
        outputs={
            b_el: solph.Flow(
                variable_costs=c_el
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
            b_h2: solph.Flow(),
            b_o2: solph.Flow(),
        },
        conversion_factors={
            b_heat: slope_heat,
            b_h2: slope_h2,
            b_o2: slope_o2
        },
        normed_offsets={
            b_heat: offset_heat,
            b_h2: offset_h2,
            b_o2: offset_o2
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
            b_h2: solph.Flow(),
            b_o2: solph.Flow(),
        },
        conversion_factors={
            b_heat: slope_heat_2,
            b_h2: slope_h2_2,
            b_o2: slope_o2_2
        },
        normed_offsets={
            b_heat: offset_heat_2,
            b_h2: offset_h2_2,
            b_o2: offset_o2_2
        }
    )

    es2.add(b_el, b_h2, b_heat, b_o2,
            source_el, sink_h2_demand, sink_heat, sink_o2,
            electrolyzer1_1, electrolyzer1_2
            )

    om = solph.Model(es2)

    myblock = po.Block()
    om.add_component("MyBlock", myblock)

    # es kann nur Ely1_1 oder Ely1_2 produzieren, nicht beide gleichzeitig
    solph.constraints.limit_active_flow_count(
        om, "flow count", [(b_el, electrolyzer1_1), (b_el, electrolyzer1_2)], lower_limit=0, upper_limit=1
    )

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

    arr = results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1] + \
          results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[:-1]
    betriebsstunden = sum(np.array(arr) > 0)
    betrieb_bei_volllast = sum(np.array(arr) == power_ely)

    volllaststunden_el = ((sum(results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1]) +
                           sum(results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[
                               :-1])) /
                          power_ely)

    # totale variable Kosten werden berechnet, indem die bezogene Strommenge mit den Strompreisen multipliziert werden
    cost_el_ely1 = sum((results[("electricity bus", "electrolyzer market 1")]["sequences"]["flow"].values[:-1] +
                        results[("electricity bus", "electrolyzer market 2")]["sequences"]["flow"].values[:-1]) * c_el)
    # annualisierte Investitionskosten werden zu den variablen Kosten addiert um die gesamten Kosten zu betrachten
    total_cost_el = cost_el_ely1 + annualized_cost
    # Berechnung der produzierten Wasserstoffmenge
    produced_h2 = sum(results[("hydrogen bus", "hydrogen demand")]["sequences"]["flow"].values[:-1])

    # Gestehungskosten werden berechnet, indem die Gesamtkosten durch die Summe der produzierten Menge dividiert wird
    lcoh2 = total_cost_el / produced_h2

    return lcoh2, df



#festlegen von sehr hohen Ausgangsgestehungskosten
min_lcoh2 = 10000000

for c_h2_virtual in range(100,150):
    lcoh2, df = find_min_lcoh2(c_h2_virtual)
    print(c_h2_virtual, lcoh2)
    if lcoh2 <= min_lcoh2:
        min_lcoh2 = lcoh2
        c_at_min = c_h2_virtual
    else:
        break

print(min_lcoh2, c_at_min)
print(df)