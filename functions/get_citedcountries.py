from www.services import *


def get_cited_countries(df, num_of_cited_countries, cited_countries_measure):
    """
    Generate a plot and table of the most cited countries.
    
    Args:
        df: A DataFrame object containing the data.
        num_of_cited_countries: The number of top cited countries to display.
        cited_countries_measure: The measure to use for ranking (either "TC" for total citations or "Average Article Citations").
        
    Returns:
        A Plotly figure object and a DataFrame of the most cited countries.
    """
    # Extract metadata tags for cited countries
    df = metaTagExtraction(df, "AU1_CO")
    df = df.get()

    if "AU1_CO" not in df.columns or df["AU1_CO"].dropna().empty:
        fig = go.Figure()
        fig.add_annotation(
            text="⚠️ Cannot Calculate Country Citations<br><br>The field <b>'AU1_CO'</b> (First Author Country) is blank or missing from your dataset.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#D9534F", family="Segoe UI, Arial"), align="center"
        )
        fig.update_layout(xaxis={"visible": False}, yaxis={"visible": False}, plot_bgcolor="rgba(245,245,245,0.5)", height=400)
        fig = go.FigureWidget(fig)
        fig._config = fig._config | {'displaylogo': False}
        return fig, pd.DataFrame(columns=["Country", "TotalCitation", "AverageArticleCitations"])
    
    # Prepare the table for ranking countries
    tab = (
        df.dropna(subset=["AU1_CO"])
        .groupby("AU1_CO", as_index=False)
        .agg(TotalCitation=("TC", "sum"), AverageArticleCitations=("TC", lambda x: round(x.sum() / len(x), 1)))
        .rename(columns={"AU1_CO": "Country"})
        .sort_values(by="TotalCitation", ascending=False)
    )

    # Convert columns to numeric to ensure correct calculations
    tab["TotalCitation"] = pd.to_numeric(tab["TotalCitation"])
    tab["AverageArticleCitations"] = pd.to_numeric(tab["AverageArticleCitations"])
    tab = tab.sort_values(by="TotalCitation", ascending=False)
    table = tab
    tab = tab.head(num_of_cited_countries)

    # Select the appropriate measure based on user input
    if cited_countries_measure == "total_cit":
        tab = tab[["Country", "TotalCitation"]]
        laby = "N. of Citations"
    else:
        tab = tab.sort_values(by="AverageArticleCitations", ascending=False)[["Country", "AverageArticleCitations"]]
        laby = "Average Article Citations"

    # Prepare data for plotting
    tab = tab.reset_index(drop=True)
    y_labels = tab["Country"]
    x_values = tab.iloc[:, 1]
    n = len(tab)

    if n == 0 or x_values.max() == 0:
        fig = go.Figure()
        
        # Inject the explicit text warning into the middle of the empty graph
        fig.add_annotation(
            text="⚠️ Cannot Generate Plot<br><br>The selected metrics contain no citation data (all records show <b>0 citations</b>).",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="#D9534F", family="Segoe UI, Arial"),
            align="center"
        )
        
        # Clean up the background layout so it looks like a clean message card
        fig.update_layout(
            xaxis={"visible": False},
            yaxis={"visible": False},
            plot_bgcolor="rgba(245,245,245,0.5)",
            paper_bgcolor="white",
            height=500
        )
        
        # Wrap it inside a FigureWidget exactly like your standard output expects
        fig = go.FigureWidget(fig)
        fig._config = fig._config | {'displaylogo': False}
        return fig, table

    fig = go.Figure()

    has_no_citations = (x_values.max() == 0)
    if has_no_citations:
        fig.add_annotation(
            text="ℹ️ Note: All identified countries have 0 citations recorded in this dataset.",
            xref="paper", yref="paper", x=0.5, y=0.95, showarrow=False,
            font=dict(size=12, color="#555555", family="Segoe UI, Arial"), align="center"
        )

    # Add thick lines from y-label to marker
    for i, (country, value) in enumerate(zip(y_labels, x_values)):
        fig.add_shape(
            type="line",
            x0=0,
            x1=value,
            y0=i,
            y1=i,
            line=dict(color="#e0e0e0", width=5),
            layer="below",
        )

    max_val = x_values.max()
    size_denominator = max_val if (max_val and max_val != 0 and not pd.isna(max_val)) else 1

    # Add scatter markers with text
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=list(range(n)),
            mode="markers+text",
            marker=dict(
                size=18 + 6 * (x_values / size_denominator),
                color=x_values,
                colorscale=[[0, "#B3D1F2"], [1, "#5567BB"]],
                line=dict(width=1, color="#E0E0E0"),
                opacity=0.95,
                showscale=False,
            ),
            text=x_values,
            textposition="top center",
            textfont=dict(color="#5567BB", size=13),
            hovertemplate=(
                "<b>Country:</b> %{customdata}<br>"
                "<b>" + laby + ":</b> %{x}<extra></extra>"
            ),
            customdata=y_labels,
        )
    )

    # Add horizontal grid lines for each country
    for i in range(n):
        fig.add_shape(
            type="line",
            x0=0,
            x1=x_values.max(),
            y0=i,
            y1=i,
            line=dict(color="#E0E0E0", width=2),
            layer="below",
        )

    # Set x-axis ticks
    max_x = x_values.max()

    if has_no_citations:
        x_ticks = [0, 1, 2]
    else:
        tick_step = 5 if max_x <= 50 else int(max_x // 10) or 1
        x_ticks = list(range(0, int(max_x) + tick_step, tick_step))
        if x_ticks[-1] < max_x:
            x_ticks.append(int(max_x))

    fig.update_yaxes(
        tickvals=list(range(n)),
        ticktext=y_labels,
        autorange="reversed",
        showgrid=False,
        title="Country",
        tickfont=dict(size=13),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#F0F0F0",
        zeroline=False,
        tickvals=x_ticks,
        title=laby,
        tickfont=dict(size=13),
    )
    fig.update_layout(
        plot_bgcolor='white',
        font=dict(color="#222222", size=14, family="Segoe UI, Arial"),
        margin=dict(l=180, r=40, t=40, b=40),
        height=50 + 90 * n,
        showlegend=False,
        hoverlabel=dict(
            bgcolor="white",
            font_size=13,
            font_family="Segoe UI, Arial",
            bordercolor="#5567BB"
        ),
        coloraxis_showscale=False,
    )
    fig = go.FigureWidget(fig)
    fig._config = fig._config | {'modeBarButtonsToRemove': ['pan', 'select', 'lasso2d', 'toImage'],
                                 'displaylogo': False}
    return fig, table
