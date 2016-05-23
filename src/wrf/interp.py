from __future__ import (absolute_import, division, print_function, 
                        unicode_literals)

import numpy as np
import numpy.ma as ma

from .extension import (interpz3d, interp2dxy, interp1d,
                        smooth2d, monotonic, vintrp, computevertcross,
                        computeinterpline)

from .metadecorators import set_interp_metadata
from .util import extract_vars, is_staggered
from .interputils import get_xy, get_xy_z_params
from .constants import Constants, ConversionFactors
from .terrain import get_terrain
from .geoht import get_height
from .temp import get_theta, get_temp, get_eth
from .pressure import get_pressure

__all__ = ["interplevel", "vertcross", "interpline", "vinterp"]

#  Note:  Extension decorator is good enough to handle left dims
@set_interp_metadata("horiz")
def interplevel(field3d, z, desiredloc, missingval=Constants.DEFAULT_FILL, 
                meta=True):
    """Return the horizontally interpolated data at the provided level
    
    field3d - the 3D field to interpolate
    z - the vertical values (height or pressure)
    desiredloc - the vertical level to interpolate at (must be same units as
    zdata)
    missingval - the missing data value (which will be masked on return)
    
    """
    r1 = interpz3d(field3d, z, desiredloc, missingval)
    masked_r1 = ma.masked_values (r1, missingval)
    
    return masked_r1

@set_interp_metadata("cross")
def vertcross(field3d, z, missingval=Constants.DEFAULT_FILL, 
              pivot_point=None, angle=None,
              start_point=None, end_point=None,
              cache=None, meta=True):
    """Return the vertical cross section for a 3D field, interpolated 
    to a verical plane defined by a horizontal line.
    
    Arguments:
        field3d - a 3D data field
        z - 3D height field
        pivot_point - a pivot point of (south_north,west_east) 
                      (must be used with angle)
        angle - the angle through the pivot point in degrees
        start_point - a start_point tuple of (south_north1,west_east1)
        end_point - an end point tuple of (south_north2,west_east2)
        
    """
    
    try:
        xy = cache["xy"]
        var2dz = cache["var2dz"]
        z_var2d = cache["z_var2d"]
    except (KeyError, TypeError):
        xy, var2dz, z_var2d = get_xy_z_params(z, pivot_point, angle,
                                              start_point, end_point)
        
    res = computevertcross(field3d, xy, var2dz, z_var2d, missingval)
    
    return ma.masked_values(res, missingval)


@set_interp_metadata("line")
def interpline(field2d, pivot_point=None, 
                 angle=None, start_point=None,
                 end_point=None, cache=None, meta=True):
    """Return the 2D field interpolated along a line.
    
    Arguments:
        field2d - a 2D data field
        pivot_point - a pivot point of (south_north,west_east)
        angle - the angle through the pivot point in degrees
        start_point - a start_point tuple of (south_north1,west_east1)
        end_point - an end point tuple of (south_north2,west_east2)
        
    """
    
    try:
        xy = cache["xy"]
    except (KeyError, TypeError):
        xy = get_xy(field2d, pivot_point, angle, start_point, end_point)
        
    return computeinterpline(field2d, xy)


@set_interp_metadata("vinterp")
def vinterp(wrfnc, field, vert_coord, interp_levels, extrapolate=False, 
            field_type=None, log_p=False, timeidx=0, method="cat", 
            squeeze=True, cache=None, meta=True):
    # Remove case sensitivity
    field_type = field_type.lower() if field_type is not None else "none"
    vert_coord = vert_coord.lower() if vert_coord is not None else "none"
        
    valid_coords = ("pressure", "pres", "p", "ght_msl", 
                    "ght_agl", "theta", "th", "theta-e", "thetae", "eth")
    
    valid_field_types = ("none", "pressure", "pres", "p", "z",
                         "tc", "tk", "theta", "th", "theta-e", "thetae", 
                         "eth", "ght")
    
    icase_lookup = {"none" : 0,
                    "p" : 1,
                    "pres" : 1,
                    "pressure" : 1,
                    "z" : 2,
                    "ght" : 2,
                    "tc" : 3, 
                    "tk" : 4,
                    "theta" : 5,
                    "th" : 5,
                    "theta-e" : 6,
                    "thetae" : 6,
                    "eth" : 6}
    
    # These constants match what's in the fortran code.  
    rgas    = 287.04     #J/K/kg
    ussalr  = .0065      # deg C per m, avg lapse rate
    sclht   = rgas*256./9.81
    
    # interp_levels might be a list or tuple, make a numpy array
    if not isinstance(interp_levels, np.ndarray):
        interp_levels = np.asarray(interp_levels, np.float64)
        
    # TODO: Check if field is staggered
    if is_staggered(field, wrfnc):
        raise RuntimeError("Please unstagger field in the vertical")
    
    # Check for valid coord
    if vert_coord not in valid_coords:
        raise RuntimeError("'%s' is not a valid vertical "
                           "coordinate type" %  vert_coord)
    
    # Check for valid field type
    if field_type not in valid_field_types:
        raise RuntimeError("'%s' is not a valid field type" % field_type)
    
    log_p_int = 1 if log_p else 0
    
    icase = 0
    extrap = 0
    
    if extrapolate:
        extrap = 1
        icase = icase_lookup[field_type]
    
    # Extract vriables
    #timeidx = -1 # Should this be an argument?
    ncvars = extract_vars(wrfnc, timeidx, ("PSFC", "QVAPOR", "F"), 
                          method, squeeze, cache, meta=False)
    
    sfp = ncvars["PSFC"] * ConversionFactors.PA_TO_HPA
    qv = ncvars["QVAPOR"]
    coriolis = ncvars["F"]
    
    terht = get_terrain(wrfnc, timeidx, units="m", 
                        method=method, squeeze=squeeze, cache=cache)
    t = get_theta(wrfnc, timeidx,  units="k", 
                  method=method, squeeze=squeeze, cache=cache)
    tk = get_temp(wrfnc, timeidx, units="k",  
                  method=method, squeeze=squeeze, cache=cache)
    p = get_pressure(wrfnc, timeidx, units="pa",  
                     method=method, squeeze=squeeze, cache=cache)
    ght = get_height(wrfnc, timeidx, msl=True, units="m", 
                     method=method, squeeze=squeeze, cache=cache)
    ht_agl = get_height(wrfnc, timeidx, msl=False, units="m",
                        method=method, squeeze=squeeze, cache=cache)
    
    smsfp = smooth2d(sfp, 3)        
        
    # Vertical coordinate type
    vcor = 0
    
    if vert_coord in ("pressure", "pres", "p"):
        vcor = 1
        vcord_array = p * ConversionFactors.PA_TO_HPA
        
    elif vert_coord == "ght_msl":
        vcor = 2
        vcord_array = np.exp(-ght/sclht)
        
    elif vert_coord == "ght_agl":
        vcor = 3
        vcord_array = np.exp(-ht_agl/sclht)
    
    elif vert_coord in ("theta", "th"):
        vcor = 4
        idir = 1
        icorsw = 0
        delta = 0.01
        
        p_hpa = p * ConversionFactors.PA_TO_HPA
        
        vcord_array = monotonic(t, p_hpa, coriolis, idir, delta, icorsw)
        
        # We only extrapolate temperature fields below ground 
        # if we are interpolating to pressure or height vertical surfaces.
        
        icase = 0 
        
    elif vert_coord in ("theta-e", "thetae", "eth"):
        vcor = 5
        icorsw = 0
        idir = 1
        delta = 0.01
        
        eth = get_eth(wrfnc, timeidx)
        
        p_hpa = p * ConversionFactors.PA_TO_HPA
        
        vcord_array = monotonic(eth, p_hpa, coriolis, idir, delta, icorsw)
        # We only extrapolate temperature fields below ground if we are
        # interpolating to pressure or height vertical surfaces
        icase = 0
    
    # Set the missing value
    if isinstance(field, ma.MaskedArray):
        missing = field.fill_value
    else:
        missing = Constants.DEFAULT_FILL
    
    if (field.shape != p.shape):
        raise ValueError("'field' shape does not match other variable shapes. "
                         "Verify that the 'timeidx' parameter matches the "
                         "same value used when extracting the 'field' "
                         "variable.")
            
    res = vintrp(field, p, tk, qv, ght, terht, sfp, smsfp,
                 vcord_array, interp_levels,
                 icase, extrap, vcor, log_p_int, missing)
    
    return ma.masked_values(res, missing)

# Thin wrappers around fortran calls which allow for metadata
# Move to the new routines module
# TODO:  Rename after the extensions are renamed
@set_interp_metadata("horiz")
def wrap_interpz3d(field3d, z, desiredloc, missingval, meta=True):
    return interpz3d(field3d, z, desiredloc, missingval)


@set_interp_metadata("2dxy")
def wrap_interp2dxy(field3d, xy, meta=True):
    return interp2dxy(field3d, xy)


@set_interp_metadata("1d")
def wrap_interp1d(v_in, z_in, z_out, missingval, meta=True):
    return interp1d(v_in, z_in, z_out, missingval)

    
    
    
    