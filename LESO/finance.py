# finance.py
import LESO.defaultvalues as default
from pyomo.environ import value

def wacc(equity_share, interest, return_on_investment, corporate_tax):
    """
    Weighted Average Cost of Capital
    Best but perhaps to detailed representation for cost of capital. 
    """
    e = equity_share
    d = 1 - e
    i = interest
    roi = return_on_investment
    t = corporate_tax
    tf = 1-t

    wi = e*roi + d*i*tf

    return wi

def rdr(interest, exp_inflation_rate, **kwargs):
    """
    Real Discount Rate
    This allows to factor out inflation out of economic analysis
    """

    i = interest
    f = exp_inflation_rate
    
    ri = (i-f)/(1+f)

    return ri

def crf(interest, lifetime):
    """
    Capital Recovery Factor
    Recommended use of rdr to calculate real discount rate (actual cost of interest)
    --> crf = 1/annuity
        --> CAPEX*crf == CAPEX / annuity
    """
    
    i = interest
    n = lifetime
    if n is None:
        ci = 1
    else:
        ci = (i*(1 + i)**n)/((1 + i)**n - 1)

    return ci

def tco(component, eM):
    """
    Total Cost of Ownership
    """
    pM = eM.model # extract pyomo model from enery model
    system = eM # energy model is system
    
    if component.capex != 0:
        unit_capex =    component.capex + (
                        system.lifetime - component.lifetime ) / (
                        component.lifetime ) * component.replacement
                        # linear replacement assumption
    else:
        unit_capex = 0
    
    lifetime_fixed_cost = component.opex * system.lifetime #  fixed operation expences over lifetime
    pyoVar = component.pyoVar # scaling factor in optimization issue
    lifetime_variable_cost = component.get_variable_cost(pM) * system.lifetime # variable operation expences over lifetime
    
    objective = system.crf*(
                (unit_capex + lifetime_fixed_cost)*pyoVar +
                lifetime_variable_cost
                )
                # use crf to discount all cashflows over the system lifetime
                # and come to annualized cash flows
    
    return objective

def osc(component, eM):
    """
    Overnight system cost :: applicable to any large scale optimization issues.
        Meaning of outcome:
            anything below zero means profitable without subsidies
            anything above zero means that business cases are not atractive without subsidies
    """
    pM = eM.model # extract pyomo model from enery model
    system = eM # energy model is system
    
    if hasattr(component, "crf"):
        crf = component.crf 
        unit_capex = component.capex

    else:
        crf = system.crf
        
        if component.capex != 0:
            unit_capex =    component.capex + (
                            system.lifetime - component.lifetime ) / (
                            component.lifetime ) * component.replacement
                            # linear replacement assumption
        
        else:
            unit_capex = 0
    
    fixed_cost = component.opex # without system lifetime, only the first year
    if component.dof:
        scaling_factor = component.pyoVar # scaling factor in optimization issue
    else:
        scaling_factor = getattr(component, "installed", 0)

    variable_cost = component.get_variable_cost(pM) # without system lifetime, only the first year 

    objective = (crf*(unit_capex)+fixed_cost)*scaling_factor + variable_cost
                # use crf to discount *only investment* over the system lifetime
                # and add all operation (yearly) cost to come to overnight system cost
    
    return objective

def profit(component, eM):
    """
    Maximizing the profit is minimizing cost; negative values are pofitable; otherwise not. 
        Adviced to use in combination with aditional ROI constraint. 
    """
    pM = eM.model # extract pyomo model from enery model
    system = eM
    
    fixed_cost = component.opex # without system lifetime, only the first year
    pyoVar = component.pyoVar # scaling factor in optimization issue
    variable_cost = component.get_variable_cost(pM) # without system lifetime, only the first year 
    
    objective = fixed_cost*pyoVar + variable_cost

    return objective

def investment_cost(component, eM):
    """
    Simple investment cost definition
    """
    if component.dof:
        investment_cost = component.capex * component.pyoVar
    else:
        investment_cost = component.capex * getattr(component, 'installed', 0)
    return investment_cost

def roi(eM):
    """
    Calculate the roi
    """
    system = eM
    pM = eM.model # extract pyomo model from enery model

    net_income = -sum( # <-- notice the minus sign!
            component.opex * component.pyoVar + component.get_variable_cost(pM)
            for component in system.components
    )

    total_investment_cost = sum(
        investment_cost(component, eM)
        for component in system.components
    )
    
    roi_ = net_income/total_investment_cost

    return roi_

def lcoe():
    """
    Levelized Cost Of Energy
    """
    raise NotImplementedError('Lcoe does not exist (yet!)')
    pass

## Ex post methods
"""
These functions simply wrap objective functions to a numeric value output.
    Can only be applied after optimization!
"""

def determine_component_net_profit(component, eM):
    """ex post determination method of profit"""
    return -value(profit(component, eM)) # <-- notice the minus here

def determine_component_investment_cost(component, eM):
    """ex post determination method of roi"""
    return value(investment_cost(component, eM))

def determine_roi(eM):
    """ex post determination method of roi"""
    return value(roi(eM))

def determine_total_investment_cost(eM):
    """sums component investment over all components"""
    return sum(
        determine_component_investment_cost(component, eM)
        for component in eM.components
    )

def determine_total_net_profit(eM):
    """sums component investment over all components"""
    return sum(
        determine_component_net_profit(component, eM)
        for component in eM.components
    )

def set_finance_variables(obj, system=None):
    """
    Sets all derived financial variables based on either component or system level financial parameters.
    """

    f = get_cs_attr(obj, "exp_inflation_rate", system)
    i = get_cs_attr(obj, "interest", system)
    l = get_cs_attr(obj, "lifetime", system)
    rrr = get_cs_attr(obj, "req_rate_of_return", system)
    tax = get_cs_attr(obj, "corporate_tax", system)
    eqs = get_cs_attr(obj, "equity_share", system)

    if l is not None and l != 0:
        obj.wacc = wacc(eqs, i, rrr, tax) # TODO
        obj.rdr = rdr(obj.wacc, f)
        obj.crf = crf(obj.rdr, l)
        obj.annuity = 1/obj.crf
    pass

def get_cs_attr(object, attr, system=None):
    """
    Get component or system attribute
        1. component attribute value if pressent
        2. system attribute value if pressent
        3. fallback to default value dict in default values
    """

    try:
        value = getattr(object, attr)
    except AttributeError:
        if system is not None:
            value = getattr(system, attr)
        else:
            value = default.system_parameters.get(attr)

    return value

def functionmapper(objective):

    sdict = {
        'tco': tco,
        'lcoe': lcoe,
        'osc': osc,
        'profit': profit,
    }

    return sdict[objective]