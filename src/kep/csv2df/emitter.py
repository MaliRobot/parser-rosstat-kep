"""Emitting datapoints from tables."""

import re
import pandas as pd


__all__ = ['Emitter']


COMMENT_CATCHER = re.compile("\D*(\d+[.,]?\d*)\s*(?=\d\))")


def to_float(text: str, i=0):
    """Convert *text* to float() type.

    Returns:
        Float value, or False if not sucessful.
    """
    i += 1
    if i > 5:
        raise ValueError("Max recursion depth exceeded on '{}'".format(text))
    if not text:
        return False
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        # note: order of checks important
        if " " in text.strip():  # get first value '542,0 5881)'
            return to_float(text.strip().split(" ")[0], i)
        if ")" in text:  # catch '542,01)'
            match_result = COMMENT_CATCHER.match(text)
            if match_result:
                text = match_result.group(0)
                return to_float(text, i)
        if text.endswith(".") or text.endswith(","):  # catch 97.1,
            return to_float(text[:-1], i)
        return False


class DatapointMaker:
    """Factory to make dictionaries representing a datapoint."""

    def __init__(self, year, label):
        self.year = year
        self.label = label
        self.freq = False
        self.value = False
        self.period = False

    def set_value(self, x):
        if x:  # (ID) if x can have value of 0 then `else` will be executed.
            self.value = to_float(x)
        else:
            self.value = None

    def make(self, freq: str, x: float, period=False):
        self.freq = freq
        self.set_value(x)
        self.period = period
        return self.as_dict()

    def get_date(self):
        # annual
        if self.freq == 'a':
            return pd.Timestamp(str(self.year)) + pd.offsets.YearEnd()
        # qtr
        year = int(self.year)
        if self.freq == 'q':
            month = int(self.period) * 3
            base = pd.Timestamp(year, month, 1)
            return base + pd.offsets.QuarterEnd()
        #  month
        elif self.freq == 'm':
            month = int(self.period)
            base = pd.Timestamp(year, month, 1)
            return base + pd.offsets.MonthEnd()

    def as_dict(self):
        # FIXME: why do we need year, qtr and month here?
        basedict = dict(year=int(self.year),
                        label=self.label,
                        freq=self.freq,
                        value=self.value,
                        time_index=self.get_date())
        if self.freq == 'q':
            basedict.update(dict(qtr=self.period))
        elif self.freq == 'm':
            basedict.update(dict(month=self.period))
        return basedict


def import_table_values_by_frequency(tables):
    """Return lists of annual, quarterly and monthly values
       from a list of Table() instances.
    """
    a, q, m = [], [], []
    for table in tables:
        # safeguard - all tables must be definaed at this point
        if not table.is_defined():
            raise ValueError('Undefined table:\n{}'.format(table))
        splitter = table.splitter_func
        for row in table.datarows:
            factory = DatapointMaker(row.get_year(), table.label)
            a_value, q_values, m_values = splitter(row.data)
            if a_value:
                a.append(factory.make('a', a_value))
            if q_values:
                qs = [factory.make('q', val, t + 1)
                      for t, val in enumerate(q_values) if val]
                q.extend(qs)
            if m_values:
                ms = [factory.make('m', val, t + 1)
                      for t, val in enumerate(m_values) if val]
                m.extend(ms)
    return a, q, m


def get_duplicates(df):
    if df.empty:
        return df
    else:
        return df[df.duplicated(keep=False)]


class Emitter:
    """Emitter converts tables to dataframes.

       Method:
           .get_dataframe(freq)
    """

    def __init__(self, tables):
        a, q, m = import_table_values_by_frequency(tables)
        self.selector = dict(a=a, q=q, m=m)

    def _get_raw_dataframe(self, freq):
        df = pd.DataFrame(self.selector[freq])
        if df.empty:
            return pd.DataFrame()
        # check for duplicates
        dups = get_duplicates(df)
        if not dups.empty:
            raise ValueError("Duplicate rows found {}".format(dups))
        # reshape
        df = df.pivot(columns='label', values='value', index='time_index')
        # delete some internals for better view
        df.columns.name = None
        df.index.name = None
        # add year
        df.insert(0, "year", df.index.year)
        # add period
        if freq == "q":
            df.insert(1, "qtr", df.index.quarter)
        if freq == "m":
            df.insert(1, "month", df.index.month)    
        return df    

    def get_dataframe(self, freq):
        df = self._get_raw_dataframe(freq)
        if df.empty:
            return pd.DataFrame()
        # transform variables:
        if freq == "a":
            df = rename_accum(df)
        if freq == "q":
            df = deaccumulate(df, first_month=3)
        if freq == "m":
            df = deaccumulate(df, first_month=1)
        return df

# government revenue and expense transformation
def rename_accum(df):
    return df.rename(mapper = lambda s: s.replace('_ACCUM',''), axis=1)   

def deacc_main(df, first_month):
    # save start of year values
    original_start_year_values = df[df.index.month == first_month].copy()
    # take a difference
    df = df.diff()
    # write back start of year values (January in monthly data, March in qtr data)
    ix = original_start_year_values.index
    df.loc[ix, :] = original_start_year_values
    return df 

def deaccumulate(df, first_month):
    varnames = [vn for vn in df.columns if vn.startswith('GOV') and ("ACCUM" in vn)]
    df[varnames] = deacc_main(df[varnames], first_month)
    return rename_accum(df)

# def deaccumulate_qtr(df):
#     return deaccumulate(df, first_month=3)

# def deaccumulate_month(df):
#     return deaccumulate(df, first_month=1)

if __name__ == '__main__':    
    from kep.config import InterimCSV
    from kep.definitions.definitions import DEFINITION

    def tables(year, month, parsing_definition=DEFINITION):
        csv_text = InterimCSV(year, month).text()
        return parsing_definition.attach_data(csv_text).tables

    tables = tables(2016, 10)
    a, q, m = import_table_values_by_frequency(tables)
    e = Emitter(tables)
    dfa = e.get_dataframe('a')
    dfq = e.get_dataframe('q')
    dfm = e.get_dataframe('m')

    from kep.csv2df.rowstack import text_to_rows 
    from kep.csv2df.parser import extract_tables, split_to_tables
    from kep.csv2df.specification import Def
    # input data
    csv_segment = text_to_rows("""Объем ВВП, млрд.рублей / Gross domestic product, bln rubles
    1999	4823	901	1102	1373	1447
    2000	7306	1527	1697	2038	2044""")
    

    # input instruction
    commands = dict(var="GDP", header="Объем ВВП", unit=["bln_rub"])
    pdef = Def(commands, units={"млрд.рублей": "bln_rub"})

    tables2 = split_to_tables(csv_segment) #, pdef)
    #e2 = Emitter(tables2)
    #dfa2 = e2.get_dataframe(freq='a')
    #dfq2 = e2.get_dataframe(freq='q')
    #dfm2 = e2.get_dataframe(freq='m')


