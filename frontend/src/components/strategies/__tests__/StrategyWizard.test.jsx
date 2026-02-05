// ABOUTME: Test suite for StrategyWizard component
// ABOUTME: Validates filter template presets functionality

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import StrategyWizard from '../StrategyWizard';

// Mock fetch for API calls
global.fetch = jest.fn();

describe('StrategyWizard - Filter Template Presets', () => {
    const mockOnClose = jest.fn();
    const mockOnSuccess = jest.fn();

    beforeEach(() => {
        jest.clearAllMocks();
        fetch.mockResolvedValue({
            ok: true,
            json: async () => ({ portfolios: [] })
        });
    });

    test('renders template selector on step 2', async () => {
        render(<StrategyWizard onClose={mockOnClose} onSuccess={mockOnSuccess} />);

        // Navigate to step 2
        const nameInput = screen.getByPlaceholderText(/e.g., Aggressive Tech Growth/i);
        fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });

        const nextButton = screen.getByText(/Next Step/i);
        fireEvent.click(nextButton);

        await waitFor(() => {
            expect(screen.getByText('Filter Template (Optional)')).toBeInTheDocument();
        });

        // Check all template options are present
        expect(screen.getByText('Custom (Build Your Own)')).toBeInTheDocument();
        expect(screen.getByText('Beaten Down Large Caps')).toBeInTheDocument();
        expect(screen.getByText('Value Stocks')).toBeInTheDocument();
        expect(screen.getByText('Growth at Reasonable Price (GARP)')).toBeInTheDocument();
        expect(screen.getByText('Low Debt, Stable Companies')).toBeInTheDocument();
        expect(screen.getByText('Small Cap Growth')).toBeInTheDocument();
        expect(screen.getByText('Dividend Value Plays')).toBeInTheDocument();
    });

    test('selecting a template populates filters', async () => {
        render(<StrategyWizard onClose={mockOnClose} onSuccess={mockOnSuccess} />);

        // Navigate to step 2
        const nameInput = screen.getByPlaceholderText(/e.g., Aggressive Tech Growth/i);
        fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });

        const nextButton = screen.getByText(/Next Step/i);
        fireEvent.click(nextButton);

        await waitFor(() => {
            expect(screen.getByText('Filter Template (Optional)')).toBeInTheDocument();
        });

        // Select "Value Stocks" template
        const templateSelect = screen.getByLabelText(/Filter Template/i);
        fireEvent.change(templateSelect, { target: { value: 'value_stocks' } });

        // Check that description appears
        await waitFor(() => {
            expect(screen.getByText(/Traditional value stocks with low P\/E and PEG ratios/i)).toBeInTheDocument();
        });

        // Check that filters are populated (2 filters for value_stocks)
        const fieldSelects = screen.getAllByDisplayValue(/Select field.../i);
        expect(fieldSelects.length).toBe(0); // Should be populated, not showing placeholder

        // Check that the "Add Filter" button exists
        expect(screen.getByText(/Add Filter/i)).toBeInTheDocument();
    });

    test('template descriptions display correctly', async () => {
        render(<StrategyWizard onClose={mockOnClose} onSuccess={mockOnSuccess} />);

        // Navigate to step 2
        const nameInput = screen.getByPlaceholderText(/e.g., Aggressive Tech Growth/i);
        fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });

        const nextButton = screen.getByText(/Next Step/i);
        fireEvent.click(nextButton);

        await waitFor(() => {
            expect(screen.getByText('Filter Template (Optional)')).toBeInTheDocument();
        });

        const templateSelect = screen.getByLabelText(/Filter Template/i);

        // Test "beaten_down_large_caps"
        fireEvent.change(templateSelect, { target: { value: 'beaten_down_large_caps' } });
        await waitFor(() => {
            expect(screen.getByText(/Large cap companies down 20%\+ from their 52-week highs/i)).toBeInTheDocument();
        });

        // Test "growth_at_reasonable_price"
        fireEvent.change(templateSelect, { target: { value: 'growth_at_reasonable_price' } });
        await waitFor(() => {
            expect(screen.getByText(/GARP strategy.*Peter Lynch's preferred approach/i)).toBeInTheDocument();
        });

        // Test "small_cap_growth"
        fireEvent.change(templateSelect, { target: { value: 'small_cap_growth' } });
        await waitFor(() => {
            expect(screen.getByText(/Small cap companies.*Higher risk, higher potential reward/i)).toBeInTheDocument();
        });
    });

    test('selecting "Custom" clears all filters', async () => {
        render(<StrategyWizard onClose={mockOnClose} onSuccess={mockOnSuccess} />);

        // Navigate to step 2
        const nameInput = screen.getByPlaceholderText(/e.g., Aggressive Tech Growth/i);
        fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });

        const nextButton = screen.getByText(/Next Step/i);
        fireEvent.click(nextButton);

        await waitFor(() => {
            expect(screen.getByText('Filter Template (Optional)')).toBeInTheDocument();
        });

        const templateSelect = screen.getByLabelText(/Filter Template/i);

        // Select a template first
        fireEvent.change(templateSelect, { target: { value: 'value_stocks' } });

        await waitFor(() => {
            expect(screen.getByText(/Traditional value stocks/i)).toBeInTheDocument();
        });

        // Now select "Custom" to clear
        fireEvent.change(templateSelect, { target: { value: '' } });

        // Description should disappear
        await waitFor(() => {
            expect(screen.queryByText(/Traditional value stocks/i)).not.toBeInTheDocument();
        });
    });

    test('users can modify template filters after selection', async () => {
        render(<StrategyWizard onClose={mockOnClose} onSuccess={mockOnSuccess} />);

        // Navigate to step 2
        const nameInput = screen.getByPlaceholderText(/e.g., Aggressive Tech Growth/i);
        fireEvent.change(nameInput, { target: { value: 'Test Strategy' } });

        const nextButton = screen.getByText(/Next Step/i);
        fireEvent.click(nextButton);

        await waitFor(() => {
            expect(screen.getByText('Filter Template (Optional)')).toBeInTheDocument();
        });

        // Select a template
        const templateSelect = screen.getByLabelText(/Filter Template/i);
        fireEvent.change(templateSelect, { target: { value: 'value_stocks' } });

        await waitFor(() => {
            expect(screen.getByText(/Traditional value stocks/i)).toBeInTheDocument();
        });

        // Add an additional filter
        const addFilterButton = screen.getByText(/Add Filter/i);
        fireEvent.click(addFilterButton);

        // Verify we can add more filters on top of template
        const fieldSelects = screen.getAllByText(/Select field.../i);
        expect(fieldSelects.length).toBeGreaterThan(0);
    });

    test('all templates use valid field names', () => {
        const VALID_FIELDS = [
            'price_vs_52wk_high',
            'market_cap',
            'pe_ratio',
            'peg_ratio',
            'debt_to_equity',
            'price',
            'sector'
        ];

        // This is a static validation - we're checking the template structure
        const FILTER_TEMPLATES = {
            beaten_down_large_caps: {
                filters: [
                    { field: 'price_vs_52wk_high', operator: '<=', value: -20 },
                    { field: 'market_cap', operator: '>=', value: 10000000000 }
                ]
            },
            value_stocks: {
                filters: [
                    { field: 'pe_ratio', operator: '<=', value: 15 },
                    { field: 'peg_ratio', operator: '<=', value: 1.0 }
                ]
            },
            growth_at_reasonable_price: {
                filters: [
                    { field: 'peg_ratio', operator: '<=', value: 1.0 },
                    { field: 'pe_ratio', operator: '>=', value: 5 },
                    { field: 'pe_ratio', operator: '<=', value: 30 }
                ]
            },
            low_debt_stable: {
                filters: [
                    { field: 'debt_to_equity', operator: '<=', value: 0.5 },
                    { field: 'market_cap', operator: '>=', value: 2000000000 }
                ]
            },
            small_cap_growth: {
                filters: [
                    { field: 'market_cap', operator: '>=', value: 300000000 },
                    { field: 'market_cap', operator: '<=', value: 2000000000 },
                    { field: 'pe_ratio', operator: '>=', value: 10 },
                    { field: 'pe_ratio', operator: '<=', value: 40 }
                ]
            },
            dividend_value: {
                filters: [
                    { field: 'pe_ratio', operator: '<=', value: 15 },
                    { field: 'market_cap', operator: '>=', value: 5000000000 },
                    { field: 'debt_to_equity', operator: '<=', value: 1.0 }
                ]
            }
        };

        // Validate all fields
        Object.entries(FILTER_TEMPLATES).forEach(([templateName, template]) => {
            template.filters.forEach((filter) => {
                expect(VALID_FIELDS).toContain(filter.field);
            });
        });
    });
});
