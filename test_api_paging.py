#!/usr/bin/env python3
"""
Test suite for API paging fix in NRN data loader.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import geopandas as gpd
from shapely.geometry import LineString


class TestAPIPaging(unittest.TestCase):
    """Tests for API paging logic"""
    
    def setUp(self):
        """Set up test fixtures"""
        try:
            from nrn_data_loader import NRNDataLoader
            self.loader = NRNDataLoader()
        except ImportError:
            self.skipTest("NRN Data Loader not available")
    
    def create_mock_features(self, start_id, count):
        """Create mock GeoJSON features"""
        features = []
        for i in range(count):
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[-123.0 + i*0.001, 49.0], [-123.0 + i*0.001, 49.001]]
                },
                'properties': {
                    'id': start_id + i,
                    'name': f'Road_{start_id + i}'
                }
            })
        return features
    
    @patch('nrn_data_loader.requests.get')
    def test_paging_continues_with_full_pages(self, mock_get):
        """Test that paging continues when receiving full pages of data"""
        from nrn_data_loader import NRNDataLoader
        
        loader = NRNDataLoader()
        
        # Mock layer info response
        layer_info_response = Mock()
        layer_info_response.json.return_value = {'maxRecordCount': 1000}
        layer_info_response.raise_for_status = Mock()
        
        # Mock data responses - 3 pages of 1000 records each, then 500 on last page
        page1_response = Mock()
        page1_response.json.return_value = {
            'features': self.create_mock_features(0, 1000)
        }
        page1_response.raise_for_status = Mock()
        
        page2_response = Mock()
        page2_response.json.return_value = {
            'features': self.create_mock_features(1000, 1000)
        }
        page2_response.raise_for_status = Mock()
        
        page3_response = Mock()
        page3_response.json.return_value = {
            'features': self.create_mock_features(2000, 1000)
        }
        page3_response.raise_for_status = Mock()
        
        page4_response = Mock()
        page4_response.json.return_value = {
            'features': self.create_mock_features(3000, 500)
        }
        page4_response.raise_for_status = Mock()
        
        # Set up mock to return different responses for different calls
        mock_get.side_effect = [
            layer_info_response,  # Layer info call
            page1_response,       # First page
            page2_response,       # Second page
            page3_response,       # Third page
            page4_response        # Fourth page (partial)
        ]
        
        # Fetch data
        gdf = loader.fetch_layer_data(
            layer_id=35,
            layer_name='Test Layer',
            timeout=60,
            max_retries=3
        )
        
        # Verify we got all 3500 features
        self.assertIsNotNone(gdf, "Should return a GeoDataFrame")
        self.assertEqual(len(gdf), 3500, "Should have fetched all 3500 features across 4 pages")
        
        # Verify we made the right number of API calls (1 for info, 4 for data)
        self.assertEqual(mock_get.call_count, 5, "Should make 5 API calls total")
        
        print("✅ Paging continues correctly with full pages")
    
    @patch('nrn_data_loader.requests.get')
    def test_paging_stops_at_empty_response(self, mock_get):
        """Test that paging stops when receiving empty response"""
        from nrn_data_loader import NRNDataLoader
        
        loader = NRNDataLoader()
        
        # Mock layer info response
        layer_info_response = Mock()
        layer_info_response.json.return_value = {'maxRecordCount': 1000}
        layer_info_response.raise_for_status = Mock()
        
        # Mock data responses - 2 pages with data, then empty
        page1_response = Mock()
        page1_response.json.return_value = {
            'features': self.create_mock_features(0, 1000)
        }
        page1_response.raise_for_status = Mock()
        
        page2_response = Mock()
        page2_response.json.return_value = {
            'features': self.create_mock_features(1000, 1000)
        }
        page2_response.raise_for_status = Mock()
        
        page3_response = Mock()
        page3_response.json.return_value = {
            'features': []
        }
        page3_response.raise_for_status = Mock()
        
        # Set up mock
        mock_get.side_effect = [
            layer_info_response,
            page1_response,
            page2_response,
            page3_response
        ]
        
        # Fetch data
        gdf = loader.fetch_layer_data(
            layer_id=35,
            layer_name='Test Layer',
            timeout=60,
            max_retries=3
        )
        
        # Verify we got 2000 features and stopped
        self.assertIsNotNone(gdf)
        self.assertEqual(len(gdf), 2000, "Should have fetched 2000 features and stopped at empty page")
        
        print("✅ Paging stops correctly at empty response")
    
    @patch('nrn_data_loader.requests.get')
    def test_paging_stops_at_partial_page(self, mock_get):
        """Test that paging stops when receiving partial page"""
        from nrn_data_loader import NRNDataLoader
        
        loader = NRNDataLoader()
        
        # Mock layer info response
        layer_info_response = Mock()
        layer_info_response.json.return_value = {'maxRecordCount': 2000}
        layer_info_response.raise_for_status = Mock()
        
        # Mock data responses - first page full (2000), second page partial (1234)
        page1_response = Mock()
        page1_response.json.return_value = {
            'features': self.create_mock_features(0, 2000)
        }
        page1_response.raise_for_status = Mock()
        
        page2_response = Mock()
        page2_response.json.return_value = {
            'features': self.create_mock_features(2000, 1234)
        }
        page2_response.raise_for_status = Mock()
        
        # Set up mock
        mock_get.side_effect = [
            layer_info_response,
            page1_response,
            page2_response
        ]
        
        # Fetch data
        gdf = loader.fetch_layer_data(
            layer_id=35,
            layer_name='Test Layer',
            timeout=60,
            max_retries=3
        )
        
        # Verify we got 3234 features and stopped
        self.assertIsNotNone(gdf)
        self.assertEqual(len(gdf), 3234, "Should have fetched 3234 features and stopped at partial page")
        
        # Should only make 3 calls (1 info, 2 data)
        self.assertEqual(mock_get.call_count, 3, "Should make exactly 3 API calls")
        
        print("✅ Paging stops correctly at partial page")


def run_tests():
    """Run all tests"""
    print("="*80)
    print("API PAGING FIX - TEST SUITE")
    print("="*80 + "\n")
    
    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAPIPaging)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit(run_tests())
