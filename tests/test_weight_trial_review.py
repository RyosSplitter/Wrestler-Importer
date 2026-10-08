import unittest

import numpy as np

from tools.weight_trial_review import deform, map_source


def bone(index, name, parent, position):
    return dict(index=index, name=name, parent=parent, local_position=position,
                rotation=[0, 0, 0])


class WeightTrialReviewTests(unittest.TestCase):
    def model(self):
        return dict(bone_count=2, bones=[bone(0, 'root', -1, [0, 0, 0]),
                                      bone(1, 'joint', 0, [2, 0, 0])])

    def test_rest_and_child_pivot_rotation(self):
        model = self.model()
        points = np.array([[3., 0, 0], [3, 0, 0]])
        weights = np.array([[0., 1], [.5, .5]])
        np.testing.assert_allclose(deform(model, points, weights, {}), points)
        actual = deform(model, points, weights, {'joint': ('z', 90)})
        np.testing.assert_allclose(actual, [[2, 1, 0], [2.5, .5, 0]], atol=1e-12)

    def test_parent_motion_propagates_to_child(self):
        actual = deform(self.model(), np.array([[3., 0, 0]]), np.array([[0., 1]]),
                        {'root': ('z', 90)})
        np.testing.assert_allclose(actual, [[0, 3, 0]], atol=1e-12)

    def test_missing_weight_is_reported_and_redistributed_separately(self):
        source = self.model()
        source['bones'].append(bone(2, 'helper', 1, [1, 0, 0]))
        source['bone_count'] = 3
        weights = np.array([[.1, .2, .7]])
        direct, missing, redirects = map_source(source, self.model(), weights, False)
        np.testing.assert_allclose(direct, [[.1, .2]])
        np.testing.assert_allclose(missing, [.7])
        self.assertEqual(redirects, {})
        redistributed, missing, redirects = map_source(source, self.model(), weights, True)
        np.testing.assert_allclose(redistributed, [[.1, .9]])
        np.testing.assert_allclose(missing, [0])
        self.assertEqual(redirects, {'helper': 'joint'})


if __name__ == '__main__': unittest.main()
