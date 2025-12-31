// Home screen - Stock List
import { View, Text, FlatList, TouchableOpacity, StyleSheet } from 'react-native';
import { router } from 'expo-router';

const MOCK_STOCKS = [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 189.45, rating: 'Excellent' },
    { symbol: 'MSFT', name: 'Microsoft', price: 378.91, rating: 'Good' },
    { symbol: 'NVDA', name: 'NVIDIA', price: 485.09, rating: 'Excellent' },
    { symbol: 'GOOGL', name: 'Alphabet', price: 141.80, rating: 'Excellent' },
    { symbol: 'AMZN', name: 'Amazon', price: 153.42, rating: 'Fair' },
    { symbol: 'TSLA', name: 'Tesla', price: 248.50, rating: 'Weak' },
    { symbol: 'META', name: 'Meta Platforms', price: 358.23, rating: 'Good' },
];

export default function HomeScreen() {
    return (
        <View style={styles.container}>
            <Text style={styles.header}>Stock Screener</Text>
            <FlatList
                data={MOCK_STOCKS}
                keyExtractor={(item) => item.symbol}
                renderItem={({ item }) => (
                    <TouchableOpacity
                        style={styles.card}
                        onPress={() => router.push(`/stock/${item.symbol}`)}
                    >
                        <View style={styles.cardHeader}>
                            <Text style={styles.symbol}>{item.symbol}</Text>
                            <View style={[styles.badge, item.rating === 'Excellent' && styles.badgeExcellent, item.rating === 'Good' && styles.badgeGood]}>
                                <Text style={styles.badgeText}>{item.rating}</Text>
                            </View>
                        </View>
                        <Text style={styles.name}>{item.name}</Text>
                        <Text style={styles.price}>${item.price.toFixed(2)}</Text>
                    </TouchableOpacity>
                )}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: '#0F172A' },
    header: {
        fontSize: 28,
        color: '#FFFFFF',
        padding: 16,
        paddingTop: 60,
    },
    card: {
        backgroundColor: '#1E293B',
        marginHorizontal: 16,
        marginVertical: 6,
        padding: 16,
        borderRadius: 12,
    },
    cardHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    symbol: { fontSize: 18, color: '#60A5FA' },
    badge: {
        backgroundColor: '#374151',
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 8,
    },
    badgeExcellent: { backgroundColor: '#22C55E' },
    badgeGood: { backgroundColor: '#4ADE80' },
    badgeText: { color: '#FFFFFF', fontSize: 12 },
    name: { fontSize: 14, color: '#9CA3AF', marginTop: 4 },
    price: { fontSize: 20, color: '#FFFFFF', marginTop: 8 },
});
