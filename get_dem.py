import geopandas as gpd
import odc.stac
import pystac_client
from shapely import box
from xrspatial import slope, aspect, hillshade


def get_dem(collection: str,
            bbox: list,
            crs: str,
            resolution: float,
            bands: list,
            daterange: list | None = None):
    """
    This function queries the Canadian Geospatial Data Collections STAC API 
    for Digital Elevation Model (DEM) data within a specified bounding box 
    and date range, loads the relevant bands into xarray DataArrays, 
    and computes terrain derivatives such as slope, aspect, hillshade, 
    and canopy height model (if both DSM and DTM are available).
    Please note that the function assumes the presence of 'dsm' and 'dtm' bands
    in the specified collection for computing the canopy height model (CHM).
    It is mainly designed for DEM collections like "mrdem-30" that provide 
    both DSM and DTM products. However, it can be adapted for other collections
    that have similar band structures by adjusting the band names and 
    derivative calculations accordingly.

    Parameters
    ----------
    collection : str
        The STAC collection ID to search within.
    bbox : list
        The bounding box to search within, in the format [minx, miny, maxx, maxy].
    daterange : list | None
        Optional date range to filter items by, in the format [start_date, end_date].
    bands : list | None
        Optional list of band names to load from the item. If None, all bands will be loaded.
    crs : str
        The target coordinate reference system (CRS) to reproject the data to, e.g. "EPSG:3979".
    
    resolution : float
        The target resolution in the units of the specified CRS (e.g. 30 for 30m resolution).

    Returns
    -------
    elevation : xarray.DataArray
        The elevation data loaded from the STAC item, reprojected to the specified CRS.
    slope : xarray.DataArray
        The slope derived from the elevation data.
    aspect : xarray.DataArray
        The aspect derived from the elevation data.
    hillshade : xarray.DataArray
        The hillshade derived from the elevation data.
    canopy_height_model : xarray.DataArray
        The canopy height model derived from the DSM and DTM data, if both are available.
    """


    STAC_ROOT = "https://datacube.services.geo.ca/stac/api"
    catalog = pystac_client.Client.open(STAC_ROOT)

    search = catalog.search(collections=collection)
    items = search.item_collection()

    search = catalog.search(
                        collections=collection,
                        bbox=bbox)

    items = search.item_collection()

    print(f"Found {len(items)} items in AOI: {bbox}")


    bbox_gpd = gpd.GeoDataFrame([box(*bbox)], 
                                columns=["geometry"], 
                                crs="EPSG:4326")

    # project to EPSG:3979 NAD83 / Canada Atlas Lambert
    area_km2 = bbox_gpd.to_crs(crs).area.iloc[0] / 1e6
    print(f"AOI area: {area_km2:,.2f} km²")

    from odc.geo.geobox import GeoBox

    proj_extent = bbox_gpd.to_crs(crs).geometry.total_bounds
    print(f"Projected AOI bounds ({crs}): {proj_extent}")

    geobox = GeoBox.from_bbox(proj_extent,
                            crs=crs,
                            resolution=resolution)
    

    ds = odc.stac.load(items,
                    bands=bands, # <- avoid loading unnecessary data
                    geobox=geobox,
                    groupby="solar_day",
                    chunks={"x": 1000, "y": 1000} # use dask to load in manageable chunks
                    )

    # Compute the mean elevation across all time steps 
    # (if multiple items were loaded) to get a single DEM layer. 
    # This also helps to reduce noise and fill gaps if some items have 
    # missing data.
    aoi_dsm = ds.dsm.mean(dim="time", skipna=True).compute() 
    aoi_dtm = ds.dtm.mean(dim="time", skipna=True).compute()

    aoi_chm = (aoi_dsm - aoi_dtm).clip(min=0)
    
    # Compute terrain derivatives
    aoi_slope = slope(aoi_dtm)
    aoi_aspect = aspect(aoi_dtm)
    aoi_hillshade = hillshade(aoi_dtm) 

    return aoi_dsm, aoi_slope, aoi_aspect, aoi_hillshade, aoi_chm


# -------------------------
# calculate area from bbox
#--------------------------

def calc_area_km2(bbox: list, 
                  crs: str) -> float:
    """
    Calculate the area of a bounding box in square kilometers 
    after reprojecting to a specified CRS.

    Parameters
    ----------
    bbox : list
        The bounding box to calculate the area for, 
        in the format [minx, miny, maxx, maxy].
    crs : str
        The target coordinate reference system (CRS) to 
        reproject the data to, e.g. "EPSG:3979".

    Returns
    -------
    float
        The area of the bounding box in square kilometers.
    """
    bbox_gpd = gpd.GeoDataFrame([box(*bbox)], 
                                columns=["geometry"], 
                                crs="EPSG:4326")

    # project to specified CRS
    area_km2 = bbox_gpd.to_crs(crs).area.iloc[0] / 1e6


    return area_km2