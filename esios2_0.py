from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import pandas as pd
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Configure page
st.set_page_config(
    page_title="Mercado eléctrico español",
    page_icon=":zap:",
    layout="wide",
    initial_sidebar_state='expanded',
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': """
    ### Análisis PVPC  
    Herramienta para visualizar precios y mix energético del mercado eléctrico español.  
    Datos basados en PVPC (Precio Voluntario para el Pequeño Consumidor)  
    """
    }
)

st.title("Análisis del mercado eléctrico español ⚡")

col_1, col_2 = st.columns([2,3])

with col_1:
    selected_date = st.date_input("Seleccione un día",
                              value=date.today(),
                              max_value=date.today()
                              )


HEADERS = {"x-api-key": st.secrets['token']}
BASE_URL = "https://api.esios.ree.es/indicators/"

INDICATORS = {
    "pv": 84,
    "nuclear": 74,
    "wind on-shore": 82,
    "wind off-shore": 83,
    "combined-cycle": 79,
    "hydropower UGH": 71,
    "hydropower no UGH": 72,
    "concentrated solar": 85,
    "steam turbine ng": 81,
    "pumping and turbine": 73,
    "coal": 10008,
    "fuel": 80,
    "biomass": 91,
    "biogas": 92,
    "pumping consumption": 95,
    "hybrid renewable": 2131,
    "marine and geothermal": 86,
    "cogeneration": 10011,
    "fuel-gas": 10009,
    "imports": 10237,
    "exports": 10238,
    "waste": 10012,
    "oil-base products": 88,
    "mining products generation": 89,
    "other": 96,
    "waste energy": 90,
}

real_names = {
    "pv": 'Fotovoltaica',
    "nuclear": 'Nuclear',
    "wind on-shore": 'Eólica on-shore',
    "wind off-shore": 'Eólica off-shore',
    "combined-cycle": 'Ciclo combinado',
    "hydropower UGH": 'Hidráulica',
    "hydropower no UGH": 'Hidráulica UGH',
    "concentrated solar": 'Solar de concentración',
    "steam turbine ng": 'Turbina de vapor con gn',
    "pumping and turbine": 'Planta de bombeo',
    "coal": 'Carbón',
    "fuel": 'Fuel',
    "biomass": 'Biomasa',
    "biogas": 'Biogas',
    "pumping consumption": 'Consumo bombeo',
    "hybrid renewable": 'Hibridación renovables',
    "marine and geothermal": 'Marina y geotérmica',
    "cogeneration": 'Cogeneración',
    "fuel-gas": 'Fuel-gas',
    "imports": 'Importaciones',
    "exports": 'Exportaciones',
    "waste": 'Residuos',
    "oil-base products": 'Productos derivados del petróleo',
    "mining products generation": 'Generación productos mineros',
    "other": 'Otros',
    "waste energy": 'Energía residuos',
}

# Function to introduce better names for categories
def change_name(element):
    return real_names[str(element)]

# Function to convert the raw df to only values and datetime
def clean_pvpc(df):
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df["datetime"] = (df["datetime"].dt.tz_convert("Europe/Madrid").dt.tz_localize(None))
    return df[["datetime", "value"]]

# PVPC DATA
params_pvpc = {
    'start_date': str(selected_date) + 'T00:00:00',
    'end_date': str(selected_date) + 'T23:59:59',
    'time_trunc': 'hour'  # Optional: 'hour', 'day', or 'month'
}

id_pvpc = 1001
try:
    pvpc = requests.get(f'{BASE_URL}{id_pvpc}', headers=HEADERS, params=params_pvpc, timeout = 10)
    pvpc.raise_for_status()
    pvpc_data = pvpc.json()
except Exception:
    pass

df_pvpc = pd.DataFrame(pvpc_data['indicator']['values'])
df_pvpc = df_pvpc.loc[df_pvpc['geo_name'] == 'Península']
df_pvpc = clean_pvpc(df_pvpc)

max_row = df_pvpc.loc[df_pvpc['value'].idxmax()]
min_row = df_pvpc.loc[df_pvpc['value'].idxmin()]

## GENERATION DATA
# Helper to fetch a single indicator safely
def fetch_indicator(name, ind_id, params):
    try:
        res = requests.get(f"{BASE_URL}{ind_id}", headers=HEADERS, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        df_temp = pd.DataFrame(data["indicator"]["values"])
        df_temp = clean_pvpc(df_temp).rename(columns={"value": name})
        # It returns a tuple with the name and the df
        return name, df_temp.set_index("datetime")
    except Exception:
        return name, None


# Cache data fetching so changing dates is instantaneous on repeat views. Streamlit runs the code everytime something on the webpage is
# pressed. Saving the cache, we can save everything that has already been run, so it doesn't have to run again if something is pressed.
# By putting this function just beneath "@", the program knows that it doesn't have to run again unless new selected date is provided.
@st.cache_data(ttl=3600)
def load_all_generation_data(selected_date):
    params_gen = {
        "start_date": f"{selected_date}T00:00:00",
        "end_date": f"{selected_date}T23:59:59",
        "time_trunc": "hour",
    }

    gen_dfs = []
    # Execute up to 10 HTTP requests in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_indicator, name, ind_id, params_gen) for name, ind_id in INDICATORS.items()]
        for future in as_completed(futures):
            # Result: Wait until the value is finished and unwrap the result
            name, df = future.result()
            if df is not None:
                gen_dfs.append(df)

    if gen_dfs:
        gen_merged = pd.concat(gen_dfs, axis=1).fillna(0).reset_index()
        gen_merged = gen_merged.melt(id_vars="datetime", var_name="source", value_name="value")
        gen_merged["hour"] = gen_merged["datetime"].dt.strftime("%H:00")
        return gen_merged
    else:
        return pd.DataFrame() # In case of error, it still returns something and not an error


# We run the process but with an animation that starts the same moment the function starts
with st.spinner("Fetching energy data..."):
    gen_merged = load_all_generation_data(selected_date)

## SUMMARY DATA
totals = gen_merged.groupby('source')['value'].sum()
totals =totals[totals > 0] 
totals = totals.reset_index()
sum_generation = totals['value'].sum()

totals['percentage'] = totals['value'] / sum_generation * 100

totals = totals[totals['percentage'] > 5]
totals = totals.sort_values(by = ['percentage'],
                            axis = 0,
                            ascending = False)

## STREAMLIT CONFIGURATION
# First object

# Configure cols
with col_1:
    # Subheading
    st.subheader('Precio Voluntario para el Pequeño Consumidor')
    # Line chart for pvpc price
    fig = px.line(df_pvpc, x="datetime", y="value", markers=True)

    fig.update_layout(
        title="Hourly PVPC Price",
        xaxis_title="Hour",
        yaxis_title="€/MWh",
        height=400,
    )

    fig.update_xaxes(tickformat="%H",
                     tickmode = 'linear',
                     dtick = 5*3600000,
                     tickwidth = 3,
                     ticklen = 12,
                     ticks = 'outside',
                     minor = dict(
                         dtick = 1*3600000,
                         ticks = 'outside',
                         ticklen = 7,
                     )
                     )
    fig.update_traces(line_shape = 'spline', line_smoothing = 0.6)

    # Trace for Highest Price Point
    fig.add_trace(
        go.Scatter(
            x=[max_row["datetime"]],
            y=[max_row["value"]],
            mode="markers",
            marker=dict(size=12, color="red"),
            name="Max Price",
        )
    )
    # Trace for Lowest Price Point
    fig.add_trace(
        go.Scatter(
            x=[min_row["datetime"]],
            y=[min_row["value"]],
            mode="markers",
            marker=dict(size=12, color="lightblue"),
            name="Min Price",
        )
    )

    # Display plot and capture click events
    clicking = st.plotly_chart(
        fig,
        on_select="rerun",
        selection_mode="points",
        width='stretch',
    )

    # Selected point visualize. When cliking, plotly returns a dictionary 'selection' and inside it a list 'points'
    # First we get the selection from the dictionary and then the get from the list
    points = clicking.get('selection', {}).get('points', [])

    colbox1, colbox2 = st.columns([3,2])
    with colbox2:
        if points:
            selected_point = points[0]
            x = pd.to_datetime(selected_point['x'])
            x = x.strftime("%H:00h")

            y = selected_point['y']

            with st.container(border = True):
                c1,c2 = st.columns(2)
                
                c1.metric(label = 'Hour:', value = x)
                c2.metric(label = '€/MWh:', value =y)
        else:
            #st.info('Click any point to inspect the details')

            st.markdown("""
            <div style='text-align:center; padding: 2rem; color: gray;'>
                👆 <strong>Haz clic en cualquier punto</strong> del gráfico para ver detalles<br>
            </div>
            """, unsafe_allow_html=True)

    with colbox1:
        # Summary 
        st.markdown(f"""
        ### 📊 Resumen {selected_date.strftime('%d %b %Y')}
        **Max:** `{max_row['value']:.1f} €/MWh` 
        **Min:** `{min_row['value']:.1f} €/MWh`     
        **Generación:** `{sum_generation/100:.1f} GWh`  
        &nbsp;&nbsp;🥇**{change_name(totals.iloc[0]['source'])}** - `{totals.iloc[0]['value']/100:.1f} GWh` y `{totals.iloc[0]['percentage']:.1f} %` del mix  
        &nbsp;&nbsp;🥈**{change_name(totals.iloc[1]['source'])}** - `{totals.iloc[1]['value']/100:.1f} GWh` y `{totals.iloc[1]['percentage']:.1f} %` del mix  
        &nbsp;&nbsp;🥉**{change_name(totals.iloc[2]['source'])}** - `{totals.iloc[2]['value']/100:.1f} GWh` y `{totals.iloc[2]['percentage']:.1f} %` del mix  
        """)

with col_2:
    order = ['imports', 'exports','pumping consumption','nuclear','combined-cycle','steam turbine ng','coal','fuel','fuel-gas', 'hydropower UGH',
            'hydropower no UGH', 'wind on-shore', 'wind off-shore','marine and geothermal','biomass', 'biogas','waste','cogeneration','concentrated solar',
            'pv','hybrid renewable', 'pumping and turbine','oil-base product', 'mining products generation','other', 'waste energy']

    colours = {
        'imports':                  '#808080',   # gray
        'exports':                  '#a9a9a9',   # darker light-gray (also negative)
        'pumping consumption':      '#9b59b6',   # purple (negative, below axis)
        'nuclear':                  "#692778",   # yellow
        'combined-cycle':           '#f13c3c',   # orange
        'steam turbine ng':         '#d4a017',   # dark yellow
        'coal':                     '#4a4a4a',   # dark gray
        'fuel':                     '#8b4513',   # brown
        'fuel-gas':                 '#bc8f8f',   # rosy brown
        'hydropower UGH':           '#1f77b4',   # strong blue
        'hydropower no UGH':        '#5dade2',   # lighter blue
        'hydropower':               "#7bc6f8",
        'wind on-shore':            '#2ecc71',   # green
        'wind off-shore':           '#145a32',   # dark green
        'wind':                     "#47db84",   # green
        'marine and geothermal':    '#117864',   # teal-green
        'biomass':                  '#7d6608',   # olive
        'biogas':                   '#b7950b',   # mustard
        'waste':                    '#935116',   # brownish
        'waste energy':             '#a04000',   # rust
        'cogeneration':             '#ba4a00',   # burnt orange
        'concentrated solar':       "#ffeb39",   # amber
        'pv':                       "#ec7310",   # bright yellow
        'hybrid renewable':         '#48c9b0',   # teal
        'pumping and turbine':      '#af7ac5',   # light purple
        'oil-base product':         '#6e2c00',   # dark brown
        'mining products generation':'#7f8c8d',  # stone gray
        'other':                    '#bdc3c7',   # pale gray
        'renewable hybrid':         '#16a085',   # teal
    }


    st.subheader('Mix energético de generación')
    fig_gen = px.bar(gen_merged,
                    x='datetime',
                    y='value',
                    color = 'source',
                    category_orders={'source': order},
                    color_discrete_map= colours,
                    height = 700)

    fig_gen.update_layout(
        title="Hourly PVPC Price",
        xaxis_title="Hour",
        yaxis_title="€/MWh",
        xaxis = dict(
            tickangle = 0,
            tickfont = dict(size=15),
        ),
        barmode = 'relative'
    )
    
    #fig_gen.update_layout(barmode = 'relative')
    fig_gen.update_xaxes(tickformat = '%H', dtick = 3600000)

    st.plotly_chart(fig_gen, on_select = 'rerun', key = 'multi_chart')

## 2. GENERATION MIX

## 3. GENERATION SUMMARY
# Button to get the hours
st.subheader('Análisis horario de la generación')
col_date2, col_date2_2 = st.columns([2,3])
with col_date2:
    selected_hour = st.selectbox(
        'Seleccione un tramo horario: ',
        options = [f"{i:02d}:00 h" for i in range(24)],
        index = 0
    )

hour = selected_hour.split(':')[0]

# Adapt the df to one better for this pie chart
new_df = gen_merged.drop(gen_merged[gen_merged['source'].isin(['exports', 'other', 'pumping consumption'])].index)
new_df['source'] = new_df['source'].replace({
    'hydropower UGH': 'hydropower',
    'hydropower no UGH': 'hydropower',
    'wind on-shore': 'wind',
    'wind off-shore': 'wind'
})
new_df = new_df.groupby(['hour', 'source'], as_index=False)['value'].sum()

# Define the function that will return the values for each hour
def get_hourly(my_hour):
    df_hour = new_df.loc[new_df['hour'] == f'{my_hour}:00']
    sum = df_hour['value'].sum()
    df_hour['percentage'] = df_hour['value'] / sum *100

    # Get total value generation
    total_gen = df_hour['value'].sum()

    df_hour['include'] = df_hour.apply(
        lambda x: True if x['percentage'] > 2 else False,
        axis = 1)
    df_hour = df_hour[df_hour['include'] == True]

    # Append the rest of the generation
    remaining_p = 100 - df_hour['percentage'].sum()
    remaining_gen = total_gen - df_hour['value'].sum()

    last_row = pd.DataFrame([{
        'hour': df_hour['hour'].iloc[0],
        'source': 'other',
        'value': remaining_gen,
        'percentage': remaining_p,
        'include': True
    }])
    df_hour = pd.concat([df_hour, last_row], ignore_index=True)

    return df_hour

# Show everything
col_3, col_4 = st.columns([1, 1])

with col_3:
    fig_pie = px.pie(get_hourly(hour), values = 'value', names = 'source',color = 'source',color_discrete_map= colours)
    st.plotly_chart(fig_pie, width = 'stretch')

with col_4:
    df_col4 = get_hourly(hour).loc[:,['source', 'value', 'percentage']]

    st.dataframe(
        df_col4,
        width='stretch',
        hide_index=True,
        column_config={
            'source': st.column_config.TextColumn('Source'),
            'value': st.column_config.NumberColumn('Value (MWh)',format = '%.2f'),
            'percentage': st.column_config.ProgressColumn('Percentage %', format = '%1.1f', min_value = 0, max_value = 100)
        }
    )