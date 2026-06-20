import statistics
import pandas as pd
from collections import defaultdict
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from LensUsage import get_lens_usage_metadata

data = get_lens_usage_metadata()

# create dataframe from metadata dictionary structure
rows = []
for make, lenses in data.items():
    for lens, vals in lenses.items():
        fls = vals.get('focalLength', [])
        fns = vals.get('fNumber', [])
        # pair up by index where both exist; if lengths differ, create separate rows
        maxlen = max(len(fls), len(fns))
        for i in range(maxlen):
            rows.append({
                'make': make,
                'lens': lens,
                'focalLength': fls[i] if i < len(fls) else None,
                'fNumber': fns[i] if i < len(fns) else None
            })
df = pd.DataFrame(rows)

# get list of lenses per camera make
makes = sorted(df['make'].dropna().unique())
lenses_by_make = {m: sorted(df.loc[df['make'] == m, 'lens'].dropna().unique()) for m in makes}

app = Dash("Immich Lens Usage")

app.layout = html.Div([
    html.H3("Lens Usage: Focal Lengths and Apertures"),
    html.Div([
        html.Label("Camera Make"),
        dcc.Dropdown(id='make-dropdown', options=[{'label': m, 'value': m} for m in makes],
                     value=makes[0] if makes else None, clearable=False)
    ], style={'width': '200px', 'display': 'inline-block', 'margin-right': '20px'}),
    html.Div([
        html.Label("Lens Model"),
        dcc.Dropdown(id='lens-dropdown', clearable=False)
    ], style={'width': '500px', 'display': 'inline-block'}),
    html.Div(id='stats-div', style={'margin-top': '12px'}),
    dcc.Graph(id='plot')
], style={'font-family': 'Arial, sans-serif', 'margin': '20px'})

@app.callback(
    Output('lens-dropdown', 'options'),
    Output('lens-dropdown', 'value'),
    Input('make-dropdown', 'value')
)

def update_lens_options(make):
    if not make:
        return [], None
    options = [{'label': lens, 'value': lens} for lens in lenses_by_make.get(make, [])]
    # switch to first available lens of make if there is any
    values = options[0]['value'] if options else None
    return options, values

def compute_statistics(series):
    series = series.dropna()
    if series.empty:
        return {}
    return {
        'count': len(series),
        'mean': statistics.mean(series),
        'median': statistics.median(series),
        'q1': pd.Series(series).quantile(0.25),
        'q3': pd.Series(series).quantile(0.75),
        'min': min(series),
        'max': max(series)
    }

@app.callback(
    Output('stats-div', 'children'),
    Output('plot', 'figure'),
    Input('make-dropdown', 'value'),
    Input('lens-dropdown', 'value')
)

def update_plots(make, lens):
    if not make or not lens:
        return "No data", go.Figure(), go.Figure()
    # get subdataframe for selected lens and camera make
    sub = df[(df['make'] == make) & (df['lens'] == lens)]

    focal_length_series = sub['focalLength'].dropna().astype(float)
    fnumber_series = sub['fNumber'].dropna().astype(float)

    focal_length_statistics = compute_statistics(focal_length_series)
    fnumber_statistics = compute_statistics(fnumber_series)

    # statistics section with mean and median for analyzed images
    statistics_children = html.Div([
        html.B(f"{make} — {lens}"),
        html.Ul([
            html.Li(f"Number of Focal Length Datapoints: {focal_length_statistics.get('count',0)}" if focal_length_statistics else "Number of Focal Length Datapoints: N/A"),
            html.Ul([
                html.Li(f"Mean: {focal_length_statistics.get('mean', 'N/A'):.2f}" if focal_length_statistics else "Mean: N/A"),
                html.Li(f"Median: {focal_length_statistics.get('median', 'N/A'):.2f}" if focal_length_statistics else "Median: N/A")
            ]),
            html.Li(f"Number of Aperture Datapoints: {fnumber_statistics.get('count',0)}" if fnumber_statistics else "Number of Aperture Datapoints: N/A"),
            html.Ul([
                html.Li(f"Mean: {fnumber_statistics.get('mean', 'N/A'):.2f}" if fnumber_statistics else "Mean: N/A"),
                html.Li(f"Median: {fnumber_statistics.get('median', 'N/A'):.2f}" if fnumber_statistics else "Median: N/A")
            ]),
        ])
    ])

    # plot showing both focal lengths and aperture with quantiles
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    # focal lengths (left y-axis) - blue
    if not focal_length_series.empty:
        figure.add_trace(
            go.Violin(y=focal_length_series, name='Focal Length (mm)',
                      line_color='royalblue', fillcolor='rgba(65,105,225,0.2)',
                      meanline_visible=True, points=False, spanmode='hard'),
                    secondary_y=False
        )
        # focal quantile lines (blue shades)
        for qname, qval, col in [('Q1', focal_length_statistics['q1'], 'rgba(30,144,255,0.8)'),
                                 ('Q3', focal_length_statistics['q3'], 'rgba(30,144,255,0.5)')]:
            figure.add_shape(type='line', x0=-0.5, x1=0.4, y0=qval, y1=qval,
                          line=dict(color=col, width=2, dash='dash'), xref='x', yref='y')
            figure.add_annotation(x=0.45, y=qval, text=f"{qname}", showarrow=False, xanchor='left',
                               font=dict(color=col, size=10), yref='y')

    # f-number (right y-axis) - orange
    if not fnumber_series.empty:
        figure.add_trace(
            go.Violin(y=fnumber_series, name='F-Number (Aperture)',
                      line_color='darkorange', fillcolor='rgba(255,140,0,0.2)',
                      meanline_visible=True, points=False, spanmode='hard'),
                    secondary_y=True
        )
        # f-number quantile lines (orange shades)
        for qname, qval, col in [('Q1', fnumber_statistics['q1'], 'rgba(255,69,0,0.9)'),
                                 ('Q3', fnumber_statistics['q3'], 'rgba(255,165,0,0.6)')]:
            figure.add_shape(type='line', x0=0.6, x1=1.5, y0=qval, y1=qval,
                          line=dict(color=col, width=2, dash='dot'), xref='x', yref='y2')
            figure.add_annotation(x=0.55, y=qval, text=f"{qname}", showarrow=False, xanchor='left',
                               font=dict(color=col, size=10), yref='y2')

    figure.update_xaxes(showticklabels=False)
    figure.update_yaxes(title_text='Focal Length (mm)', secondary_y=False)
    figure.update_yaxes(title_text='F-Number (Aperture)', secondary_y=True, autorange='reversed')  # lower f-numbers at top
    figure.update_layout(height=520, legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0.01),
                      margin=dict(l=60, r=80, t=40, b=40))

    return statistics_children, figure

if __name__ == '__main__':
    app.run()
