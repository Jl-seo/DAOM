import { render } from '@testing-library/react';
import App from './App';
import { describe, it, expect } from 'vitest';

describe('App', () => {
    it('renders without crashing', () => {
        render(<App />);
        // Adjust this expectation based on what's actually in your App component
        // For now, we just check if it renders without error.
        expect(document.body).toBeDefined();
    });
});
