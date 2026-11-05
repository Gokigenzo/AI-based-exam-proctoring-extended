import numpy as np
from examwatch.vision import mouth_points


def test_mouth_corners_are_normalized_and_midpoint_added_in_screen_order():
    face=np.zeros(15)
    face[10:14]=[80,50,20,40]
    assert mouth_points(face,100,100)==[[.2,.4],[.5,.45],[.8,.5]]


def test_invalid_mouth_coordinates_not_drawn():
    face=np.zeros(15);face[10]=np.nan
    assert mouth_points(face,100,100)==[]
