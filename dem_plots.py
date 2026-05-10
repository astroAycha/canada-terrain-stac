"""Collection of plotting functions for
visualizing DEMs and STAC collections and items."""

import json

import geopandas as gpd
import pandas as pd
import plotly.express as px
from shapely.geometry import box, polygon


# ---------------------------
# Plot STAC collection extent
#----------------------------
def plot_collection_extent(collection_id: str,
                           collections_df: pd.DataFrame):
    """
    Plot the bounding box of a STAC collection over a satellite basemap.

    Parameters
    ----------
    collection_id : str
        The ID of the STAC collection to plot.
    collections_df : DataFrame
        DataFrame containing collection metadata, including 'id' 
        and 'spatial_extent' columns.
    """
    row = collections_df[collections_df["id"] == collection_id]
    if row.empty:
        raise ValueError(f"Collection '{collection_id}' not found.")

    # Keep in WGS84 — choropleth_map requires lon/lat GeoJSON
    gdf = gpd.GeoDataFrame(
        {"collection_id": row["id"].values},
        geometry=[box(*row["spatial_extent"].iloc[0])],
        crs="EPSG:4326")        # <- CRS from the STAC catalog


    # Derive a sensible center from the actual geometry
    centroid = gdf.geometry.iloc[0].centroid

    fig = px.choropleth_map(
        gdf,
        geojson=gdf.__geo_interface__,
        locations=gdf.index,
        hover_name="collection_id",
        map_style="satellite",
        zoom=2,
        center={"lat": centroid.y, "lon": centroid.x}, 
        title=f"STAC Collection: {collection_id} — Spatial Extent",
    )

    fig.update_traces(
        marker_opacity=0.45,
        marker_line=dict(color="gold", width=2),
    )

    fig.update_layout(
        showlegend=False,
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
    )
    
    # write to html file with embedded Plotly.js for standalone viewing
    fig.write_html(f"{collection_id}_extent.html", include_plotlyjs=True)

# ------------------------------------------
# Plot STAC item footprints and bounding box
#------------------------------------------

def plot_stac_boundaries(items_gdf: gpd.GeoDataFrame,
                        collection_id: str,
                        center_lat: float = 65,
                        center_lon: float = -95,
                        zoom: int = 3,
                        bbox: tuple = None):
    """
    Plot STAC item footprints on an interactive satellite map.

    Parameters
    ----------
    items_gdf : gpd.GeoDataFrame
        GeoDataFrame with item geometries
    collection_id : str
        STAC collection name (used in title)
    center_lat : float
        Initial map center latitude
    center_lon : float
        Initial map center longitude
    zoom : int
        Initial zoom level
    bbox : tuple, optional
        (minx, miny, maxx, maxy) bounding box to highlight in red
    """

    fig = px.choropleth_map(
        items_gdf,
        geojson=items_gdf.__geo_interface__,
        locations=items_gdf.index,
        hover_name="item_id",
        hover_data={"datetime": True},
        map_style="satellite",
        zoom=zoom,
        center={"lat": center_lat, "lon": center_lon},
        title=f"STAC Collection: {collection_id} — Item Boundaries",
    )

    fig.update_traces(
        marker=dict(line=dict(color="cyan", width=1.5), opacity=0.2)
    )

    fig.update_layout(
        showlegend=False,
        margin={"r": 0, "t": 40, "l": 0, "b": 0},
        map=dict(zoom=zoom),
    )

    # optionally overlay the AOI bounding box if provided
    if bbox is not None:
        _add_bbox(fig, bbox)

    # write to html file with embedded Plotly.js for standalone viewing
    fig.write_html(f"{collection_id}_items_boundaries.html", 
                   include_plotlyjs=True)


def _add_bbox(fig, bbox: tuple) -> None:
    """
    Overlay a red bounding box outline on an existing Plotly map figure.
    """
    minx, miny, maxx, maxy = bbox
    polygon_gpd = gpd.GeoSeries([polygon.Polygon.from_bounds(minx, miny, maxx, maxy)],
                      crs="EPSG:4326")
    fig.add_choroplethmap(
        geojson=polygon_gpd.__geo_interface__,
        locations=[0],
        z=[1],
        colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
        showscale=False,
        marker=dict(line=dict(color="red", width=2), opacity=1),
        hoverinfo="skip",
    )


# ---------------------------------
# Plot DEM rasters with hvplot
# ---------------------------------

def plot_dem_rasters(rasters: dict,
                    cmaps: dict = None,
                    plot_shaded_relief: bool = False,
                    aspect_key: str = "Aspect",
                    hillshade_key: str = "Hillshade",
                    output_file: str = "dem_rasters.html"):
    """
    Render a collection of rasters as an interactive tabbed HTML panel.

    Parameters
    ----------
    rasters : dict
        Mapping of tab label to xarray DataArray (e.g. ``{"Elevation": ds}``).
    cmaps : dict, optional
        Mapping of tab label to colormap name. Defaults to ``"viridis"`` for
        any label not specified.
    plot_shaded_relief : bool
        If True, append a "Shaded Relief" tab by compositing
        ``rasters[aspect_key]`` with ``rasters[hillshade_key]``.
    aspect_key : str
        Key in ``rasters`` to use as the base layer for shaded relief.
        Defaults to ``"Aspect"``.
    hillshade_key : str
        Key in ``rasters`` to use as the hillshade overlay layer for shaded
        relief. Defaults to ``"Hillshade"``.
    output_file : str
        Path for the output HTML file.
    """
    import hvplot.xarray  # noqa: F401 — registers .hvplot accessor on xarray objects
    import panel as pn

    if cmaps is None:
        cmaps = {}

    pn.extension(comms="vscode")

    plots = {
        label: raster.hvplot.image(geo=True,
                                   tiles="ESRI",
                                   alpha=0.8,
                                   cmap=cmaps.get(label, "viridis"),
                                   title=label,
                                   frame_width=600,
                                   frame_height=700)
        for label, raster in rasters.items()
    }

    if plot_shaded_relief:
        if aspect_key not in rasters or hillshade_key not in rasters:
            raise KeyError(
                "Shaded relief requires both aspect and hillshade in rasters: "
                f"missing rasters['{aspect_key}'] and/or rasters['{hillshade_key}']."
            )

        aspect_cmap = cmaps.get(aspect_key, "twilight")
        plots["Shaded Relief"] = (
            rasters[aspect_key].hvplot.image(geo=True, 
                                            tiles="ESRI", 
                                            alpha=0.8,
                                            cmap=aspect_cmap, 
                                            title="Shaded Relief",
                                            frame_width=600, 
                                            frame_height=700) *
            rasters[hillshade_key].hvplot.image(geo=True, 
                                                alpha=0.4,
                                                cmap="gray", 
                                                colorbar=False,
                                                frame_width=600, 
                                                frame_height=700)
                                )

    # Create a tabbed layout and save to HTML
    tabs = pn.Tabs(*plots.items(), dynamic=False)
    tabs.save(output_file, embed=True)
