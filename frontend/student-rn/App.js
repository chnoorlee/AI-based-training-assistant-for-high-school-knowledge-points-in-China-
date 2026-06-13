import 'react-native-gesture-handler'
import React from 'react'
import { NavigationContainer } from '@react-navigation/native'
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import { Text } from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { colors } from './src/theme'
import DiagnosisScreen from './src/screens/DiagnosisScreen'
import PlanScreen from './src/screens/PlanScreen'
import SolveScreen from './src/screens/SolveScreen'
import RecommendScreen from './src/screens/RecommendScreen'
import ReviewScreen from './src/screens/ReviewScreen'

const Tab = createBottomTabNavigator()
const icon = (e) => ({ color }) => <Text style={{ fontSize: 18, color }}>{e}</Text>

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.accent },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '700' },
          tabBarActiveTintColor: colors.accent,
          tabBarInactiveTintColor: '#9aa1ad',
        }}
      >
        <Tab.Screen name="诊断" component={DiagnosisScreen}
          options={{ title: '学情诊断', tabBarIcon: icon('◎') }} />
        <Tab.Screen name="规划" component={PlanScreen}
          options={{ title: 'AI 提分规划', tabBarIcon: icon('◷') }} />
        <Tab.Screen name="解题" component={SolveScreen}
          options={{ title: '苏格拉底解题', tabBarIcon: icon('✎') }} />
        <Tab.Screen name="推荐" component={RecommendScreen}
          options={{ title: '今日推荐', tabBarIcon: icon('✦') }} />
        <Tab.Screen name="错题本" component={ReviewScreen}
          options={{ title: '错题复习', tabBarIcon: icon('↻') }} />
      </Tab.Navigator>
    </NavigationContainer>
  )
}
