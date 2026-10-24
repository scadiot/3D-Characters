import numpy as np

from viewer import mathutil as mu


def test_identity_quat_gives_identity_matrix():
    assert np.allclose(mu.quat_to_mat3([0, 0, 0, 1]), np.eye(3))


def test_quat_90_deg_about_y_maps_x_to_minus_z():
    q = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    assert np.allclose(mu.quat_to_mat3(q) @ [1, 0, 0], [0, 0, -1])


def test_slerp_halfway_is_45_degrees():
    a = [0, 0, 0, 1]
    b = mu.axis_angle_quat([0, 1, 0], np.pi / 2)
    assert np.allclose(mu.slerp(a, b, 0.5), mu.axis_angle_quat([0, 1, 0], np.pi / 4))


def test_slerp_takes_shortest_path():
    a = np.array([0, 0, 0, 1.0])
    assert np.allclose(np.abs(mu.slerp(a, -a, 0.5)), [0, 0, 0, 1])


def test_trs_decompose_round_trip():
    t, r, s = [1, 2, 3], mu.axis_angle_quat([1, 1, 0], 0.7), [2, 2, 2]
    m = mu.trs_to_mat4(np.array([t]), np.array([r]), np.array([s]))[0]
    t2, r2, s2 = mu.decompose(m)
    assert np.allclose(t2, t) and np.allclose(s2, s)
    assert np.allclose(np.abs(np.dot(r2, r)), 1.0)


def test_look_at_puts_target_on_negative_z():
    v = mu.look_at(np.array([0, 0, 5.0]), np.zeros(3), np.array([0, 1.0, 0]))
    assert np.allclose(v @ [0, 0, 0, 1], [0, 0, -5, 1])
