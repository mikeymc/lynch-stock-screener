// Stock detail screen
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';

const MOCK_STOCKS = [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 189.45, rating: 'Excellent' },
    { symbol: 'MSFT', name: 'Microsoft', price: 378.91, rating: 'Good' },
    { symbol: 'NVDA', name: 'NVIDIA', price: 485.09, rating: 'Excellent' },
    { symbol: 'GOOGL', name: 'Alphabet', price: 141.80, rating: 'Excellent' },
    { symbol: 'AMZN', name: 'Amazon', price: 153.42, rating: 'Fair' },
    { symbol: 'TSLA', name: 'Tesla', price: 248.50, rating: 'Weak' },
    { symbol: 'META', name: 'Meta Platforms', price: 358.23, rating: 'Good' },
];

export default function StockDetailScreen() {
    const { symbol } = useLocalSearchParams<{ symbol: string }>();
    const stock = MOCK_STOCKS.find(s => s.symbol === symbol);

    return (
        <View style={styles.container}>
            <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
                <Text style={styles.backText}>← Back</Text>
            </TouchableOpacity>
            <View style={styles.center}>
                <Text style={styles.symbol}>{symbol}</Text>
                <Text style={styles.name}>{stock?.name}</Text>
                <Text style={styles.price}>${stock?.price.toFixed(2)}</Text>
                <View style={[styles.badge, stock?.rating === 'Excellent' && styles.badgeExcellent]}>
                    <Text style={styles.badgeText}>{stock?.rating}</Text>
                </View>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0F172A' },
    backButton: { paddingTop: 60, paddingHorizontal: 16 },
    backText: { color: '#60A5FA', fontSize: 16 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    symbol: { fontSize: 32, color: '#FFFFFF' },
    name: { fontSize: 16, color: '#9CA3AF', marginTop: 4 },
    price: { fontSize: 48, color: '#FFFFFF', marginTop: 20 },
    badge: { marginTop: 16, backgroundColor: '#374151', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 16 },
    badgeExcellent: { backgroundColor: '#22C55E' },
    badgeText: { color: '#FFFFFF', fontSize: 14 },
});
