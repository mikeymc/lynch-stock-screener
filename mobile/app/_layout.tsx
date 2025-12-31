// Use Slot instead of Stack to avoid animation bug
import { Slot } from 'expo-router';
import { View, StyleSheet } from 'react-native';
import { StatusBar } from 'expo-status-bar';

export default function RootLayout() {
    return (
        <View style={styles.container}>
            <StatusBar style="light" />
            <Slot />
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#0F172A',
    },
});
